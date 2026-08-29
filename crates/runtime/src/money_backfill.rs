//! **Idempotent** euros→cents money backfill for hubs that are already deployed (ADR-0007).
//!
//! ## Why it exists (and why it lives OUTSIDE the migration chain)
//!
//! Every money module ships its `001_init` **already in cents** (`INTEGER`): a NEW install is born
//! correct. But hubs that were **already deployed** applied the old `001` (euros, `NUMERIC`) and
//! their columns are still in euros. The new code (handlers in cents) would multiply those amounts
//! by 100 → corruption.
//!
//! It cannot be fixed with a chained `002` migration (`col = ROUND(col*100)`): it would ALSO run on
//! new installs (whose `001` already left the data in cents) → **double conversion**. That is why
//! the backfill lives **outside** `_hub_migrations`/`_hub_system_migrations`: it is a one-off data
//! conversion **per hub database**, guarded by a database-level marker, not by the schema version
//! chain.
//!
//! ## Marker (`_hub_meta`)
//!
//! A system table `_hub_meta(key TEXT PRIMARY KEY, value TEXT)` with the row
//! `('money_unit','cents')`. It is the source of truth for idempotency:
//!  - If the marker says `cents` → the backfill **does nothing** (neither on an old hub already
//!    converted nor on a new hub already marked).
//!  - If it is absent → the backfill reads **the declared type** of **every** money column present
//!    (`information_schema.columns`, see [`detect_money_unit`]) and demands unanimity:
//!      - all `INTEGER` → schema **already in cents** (new install) → only seeds the marker,
//!        **never touches data**.
//!      - all `NUMERIC`/`REAL`/decimal → old schema in **euros** → converts (`ROUND(col*100)`) and
//!        then seeds the marker.
//!      - a **mix** of the two → half-migrated hub → **no conversion, no marker, and a visible
//!        failure** (hub#1209). See [`MoneyUnit::Mixed`].
//!
//! So a new hub is NEVER converted (even the first time, before it has a marker) and an old hub is
//! converted exactly once. Once the marker is seeded, every re-run is a total no-op.
//!
//! ## Why the verdict is a CONSENSUS and not the first column (hub#1209)
//!
//! Until 2026-08-28 the **first** money column that existed sentenced the whole hub, and the
//! function returned right there. On a half-migrated hub that made the outcome depend on the order
//! of a hand-written list, with two equally silent endings: if an integer column won, the marker
//! was seeded and the modules still in euros stayed in euros **forever** (the marker turns every
//! re-run into a no-op); if a decimal column won, **every** present column was converted, including
//! the ones already in cents, **multiplying them by 100**. Reproduced against a real Postgres:
//! 999 ¢ → 99 900 ¢. That is why a mix is not resolved by picking a branch of the `if` — it is
//! **refused**.
//!
//! ## Delivery (ops)
//!
//! A subcommand of the server binary: `erplora-server --backfill-money` (see
//! `crates/server/src/main.rs`). It connects to the hub's Postgres (`HUB_DATABASE_URL`), runs
//! [`run`] and exits. SAFE to re-run.
//!
//! And its **read-only** sibling, `erplora-server --check-money-unit` ([`check_logged`],
//! hub#1209): says which unit a hub's money is declared in without writing anything, so the fleet
//! can be swept for half-migrated hubs. `--backfill-money` is no audit: on an old hub in euros it
//! **would convert**.

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::Result;
use crate::registry::now_rfc3339;

/// Clave del marcador "el dinero ya está en céntimos".
const MONEY_UNIT_KEY: &str = "money_unit";
const MONEY_UNIT_CENTS: &str = "cents";

/// **Authoritative** inventory of money columns per table (every column the new `001` left as
/// `INTEGER` cents; extracted from the modules' `001_init`, ADR-0007 §2). Does NOT include rates or
/// percentages (`tax_rate`, `discount_percent`, …) nor quantities (`quantity`) — those are `REAL`
/// and are not multiplied by 100.
///
/// Each entry: `(table, &[money columns])`. If the table does not exist in the database (module
/// not installed) it is silently ignored.
///
/// 🔴 **"Authoritative" here is a verified claim, not a promise.** That same sentence lived for
/// months next to six entries whose tables did not exist: since `declared_type()` returns `None`
/// for whatever the database lacks, a dead entry is skipped **silently** and nothing gives it away.
/// Whoever read the list could not tell which of the 32 were real, and retiring a table in a module
/// meant coming here to prove there was no live consumer (services#67, services#69). What backs the
/// word is `tests/money_columns_inventory.rs`: it goes red on a table a published `contract` already
/// retired, on one no module creates, and on a repeated column (it would be converted twice:
/// ×10 000).
///
/// ✅ **ORDER no longer decides anything** (hub#1209). Until 2026-08-28 the verdict for the whole hub
/// was dictated by the **first** money column that existed — position 0 of this list — so
/// reordering "to group things" moved the criterion that decides whether a customer's money is
/// multiplied by 100. Today [`detect_money_unit`] classifies **every** present column and demands
/// unanimity; adding, removing or reordering entries no longer changes the verdict for a given
/// database. What still matters about this list is **what** is in it: a duplicate entry would
/// convert twice (×10 000) and a missing column stays unconverted. That is pinned by
/// `tests/money_columns_inventory.rs`.
pub const MONEY_COLUMNS: &[(&str, &[&str])] = &[
    // appointments
    ("appointments_appointment", &["service_price"]),
    // cart_checkout
    ("cart_checkout_cart", &["total_amount"]),
    ("cart_checkout_item", &["unit_price", "line_total"]),
    ("cart_checkout_session", &["total_amount"]),
    // cash_register
    (
        "cash_register_session",
        &["opening_balance", "closing_balance", "expected_balance", "difference"],
    ),
    ("cash_register_movement", &["amount"]),
    ("cash_register_count", &["total"]),
    // customers
    ("customers_customer", &["total_spent"]),
    // inventory
    ("inventory_product", &["price", "cost"]),
    ("inventory_product_variant", &["price"]),
    // invoice
    ("invoice_invoice", &["base_amount", "tax_amount", "total_amount"]),
    ("invoice_invoiceitem", &["unit_price", "base_amount", "tax_amount", "total_amount"]),
    // kitchen
    ("kitchen_order", &["subtotal", "tax", "discount", "total"]),
    ("kitchen_order_item", &["unit_price", "total"]),
    // `kitchen_order_modifier` estuvo aquí y se ha ido: la retira `kitchen/migrations/postgres/007`
    // (kitchen#55) y el guard la aparta a `_deprecated_kitchen_order_modifier`, así que
    // `declared_type` no volverá a encontrarla. El suplemento con precio vive en `modifiers`
    // (ADR-0376) y su dinero lo lleva la línea de venta, no esta tabla.
    //
    // `kitchen_orders_order`, `kitchen_orders_order_item` y `kitchen_orders_order_modifier`
    // estuvieron aquí y se han ido con ellas: el módulo `kitchen_orders` se fusionó dentro de
    // `kitchen` (ADR-0014) y está archivado, así que ningún hub crea esas tablas. Sus columnas de
    // dinero son las de `kitchen_order*`, justo encima.
    //
    // `orders_order` estuvo aquí y se ha ido: el módulo `orders` no existe — nunca se publicó. La
    // entrada venía del inventario del plan de migración a céntimos, que lo daba por futuro.
    // payment_gateways
    ("payment_gateways_transaction", &["amount"]),
    ("payment_gateways_refund", &["amount_refunded"]),
    // payments
    ("payments_payment", &["amount"]),
    // pricing
    ("pricing_price_list_item", &["price"]),
    ("pricing_discount_rule", &["min_amount", "max_amount"]),
    // sales
    (
        "sales_sale",
        &["subtotal", "tax_amount", "discount_amount", "total", "amount_tendered", "change_due"],
    ),
    ("sales_sale_item", &["unit_price", "net_amount", "tax_amount", "line_total"]),
    // services
    ("services_service", &["price", "min_price", "max_price", "cost"]),
    // `services_variant` estuvo aquí y se ha ido: `services/migrations/postgres/010` la retira
    // (services#69) y el guard la aparta a `_deprecated_services_variant`. Como con `services_addon`,
    // no había nada que convertir: la tabla nunca tuvo puerta — ningún command escribía una fila.
    //
    // `services_addon` estuvo aquí y se ha ido: `services/migrations/postgres/009` la retira
    // (services#67, ADR-0376) y el guard la aparta a `_deprecated_services_addon`, así que
    // `declared_type` no volverá a encontrarla. Tampoco había nada que convertir: el módulo nunca
    // tuvo un command que escribiera una fila ahí.
    ("services_package", &["fixed_price"]),
    // staff
    ("staff_member", &["hourly_rate"]),
    ("staff_service", &["custom_price"]),
    // verifactu
    ("verifactu_record", &["base_amount", "tax_amount", "total_amount"]),
];

/// The unit a hub database's money is declared in, decided over **every** column of
/// [`MONEY_COLUMNS`] that exists (hub#1209).
///
/// The verdict used to come from the first column found, and the function returned right there: on
/// a half-migrated hub that turned list position into the criterion that decides whether a
/// customer's money is multiplied by 100. Now it is a consensus, and disagreement has its own case
/// — [`MoneyUnit::Mixed`] — instead of being settled by guessing.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MoneyUnit {
    /// No money table is installed: nothing to convert, the hub is "trivially" in cents.
    NoMoneyColumns,
    /// Every money column present is declared integer: new install.
    Cents,
    /// Every money column present is declared decimal: old hub in euros.
    Euros,
    /// Columns of BOTH kinds. Nothing is converted, nothing is marked, and it is reported: both
    /// possible readings corrupt real money in opposite directions. Carries the `table.column`
    /// names of each side so ops can act on them.
    Mixed { cents: Vec<String>, euros: Vec<String> },
}

impl MoneyUnit {
    /// The stable error that represents a mixed hub, with the columns that disagree. `None` for
    /// any verdict that can actually be applied.
    fn refusal(&self) -> Option<crate::errors::RuntimeError> {
        match self {
            Self::Mixed { cents, euros } => Some(crate::errors::RuntimeError::MoneyUnitAmbiguous {
                cents: cents.join(", "),
                euros: euros.join(", "),
            }),
            _ => None,
        }
    }
}

/// Classifies **every** money column present in the database and returns the hub's verdict.
///
/// Walks the WHOLE of [`MONEY_COLUMNS`] — never returning on the first match — and sorts each
/// existing column by its declared type ([`is_integer_type`]). The result depends only on what the
/// database holds, never on the order of the list (hub#1209). Rows do not vote: an empty table, a
/// column holding only `NULL`s or all-zero amounts is classified by its declared type like any
/// other, because the type is what the handlers will write into it tomorrow.
pub async fn detect_money_unit(db: &dyn DatabaseAdapter) -> Result<MoneyUnit> {
    let mut cents: Vec<String> = Vec::new();
    let mut euros: Vec<String> = Vec::new();
    for (table, columns) in MONEY_COLUMNS {
        for col in *columns {
            if let Some(ty) = declared_type(db, table, col).await? {
                let name = format!("{table}.{col}");
                if is_integer_type(&ty) {
                    cents.push(name);
                } else {
                    euros.push(name);
                }
            }
        }
    }
    Ok(match (cents.is_empty(), euros.is_empty()) {
        (true, true) => MoneyUnit::NoMoneyColumns,
        (false, true) => MoneyUnit::Cents,
        (true, false) => MoneyUnit::Euros,
        (false, false) => MoneyUnit::Mixed { cents, euros },
    })
}

/// Reports a mixed hub to the error registry (severity `unexpected`, see
/// [`crate::error_registry::severity_of`]) and on `stderr`. A failure nobody sees does not exist:
/// this is how ops learns that a hub was left half migrated (hub#1209). On the boot path the
/// registry has no sink yet (`install_error_reporting` runs after `ensure_system_tables`), so there
/// the `stderr` line is the one that reaches the hub's log.
fn report_mixed(err: &crate::errors::RuntimeError, source: &str) {
    eprintln!("[backfill-money] 🔴 {err}");
    crate::error_registry::report_runtime_error(err, source, None, json!({ "issue": "hub#1209" }));
}

/// Resultado del backfill (para logging por ops).
#[derive(Debug, Clone, PartialEq, Eq, Default)]
pub struct BackfillReport {
    /// `true` si ya estaba marcado en céntimos al entrar (no se hizo nada).
    pub already_marked: bool,
    /// `true` si el esquema se detectó ya en céntimos (instalación nueva) → solo se marcó.
    pub schema_already_cents: bool,
    /// Tablas que se convirtieron (euros→céntimos).
    pub converted_tables: Vec<String>,
    /// Filas totales actualizadas por la conversión.
    pub rows_updated: u64,
}

/// Asegura la tabla de metadatos (idempotente). La DDL vive en [`crate::hub_meta`], que es el
/// dueño de `_hub_meta` desde que hay más de un marcador que recordar (ADR-0212).
pub async fn ensure_meta_table(db: &dyn DatabaseAdapter) -> Result<()> {
    crate::hub_meta::ensure_table(db).await
}

/// `true` si el marcador `money_unit=cents` ya está puesto.
pub async fn is_marked_cents(db: &dyn DatabaseAdapter) -> Result<bool> {
    ensure_meta_table(db).await?;
    let mut p = Params::new();
    p.insert("key".into(), json!(MONEY_UNIT_KEY));
    let res = db.query("SELECT value FROM _hub_meta WHERE key = :key", &p).await?;
    Ok(res.rows.iter().any(|r| r["value"].as_str() == Some(MONEY_UNIT_CENTS)))
}

/// Same as [`is_marked_cents`] but **creating nothing**: if `_hub_meta` does not exist yet it
/// returns `false` instead of creating it. Used by the read-only audit [`check_logged`], which
/// cannot afford to write into a customer's database just for looking at it (hub#1209).
async fn is_marked_cents_readonly(db: &dyn DatabaseAdapter) -> Result<bool> {
    let exists = db
        .query(
            "SELECT 1 AS present FROM information_schema.tables \
             WHERE table_schema = current_schema() AND table_name = '_hub_meta'",
            &Params::new(),
        )
        .await?;
    if exists.rows.is_empty() {
        return Ok(false);
    }
    let mut p = Params::new();
    p.insert("key".into(), json!(MONEY_UNIT_KEY));
    let res = db.query("SELECT value FROM _hub_meta WHERE key = :key", &p).await?;
    Ok(res.rows.iter().any(|r| r["value"].as_str() == Some(MONEY_UNIT_CENTS)))
}

/// The statement that seeds the `money_unit=cents` marker (idempotent: UPSERT, `key` is the PK —
/// ADR-0154, Postgres-only). Exposed as an op so [`run`] can commit it in the SAME transaction as
/// the conversion it seals.
fn mark_cents_op() -> (String, Params) {
    let mut p = Params::new();
    p.insert("key".into(), json!(MONEY_UNIT_KEY));
    p.insert("value".into(), json!(MONEY_UNIT_CENTS));
    (
        "INSERT INTO _hub_meta (key, value) VALUES (:key, :value) \
         ON CONFLICT (key) DO UPDATE SET value = :value"
            .to_string(),
        p,
    )
}

/// Seeds the `money_unit=cents` marker on its own (idempotent).
async fn mark_cents(db: &dyn DatabaseAdapter) -> Result<()> {
    let (sql, p) = mark_cents_op();
    db.execute(&sql, &p).await?;
    Ok(())
}

/// Tipo declarado de una columna, o `None` si la tabla/columna no existe (módulo no instalado).
/// Postgres: `information_schema.columns` (ADR-0154).
async fn declared_type(
    db: &dyn DatabaseAdapter,
    table: &str,
    column: &str,
) -> Result<Option<String>> {
    // Postgres-only (ADR-0154). `current_schema()` acota al esquema activo del hub (en prod es
    // `public`; en los tests, el esquema efímero) para no leer columnas de otro esquema homónimo.
    let mut p = Params::new();
    p.insert("t".into(), json!(table));
    p.insert("c".into(), json!(column));
    let res = db
        .query(
            "SELECT data_type FROM information_schema.columns \
             WHERE table_schema = current_schema() AND table_name = :t AND column_name = :c",
            &p,
        )
        .await?;
    Ok(res.rows.first().and_then(|r| r["data_type"].as_str().map(|s| s.to_string())))
}

/// `true` si el tipo declarado ya es **entero** (esquema en céntimos: el `001` nuevo declara
/// `INTEGER`). Cualquier otra cosa (NUMERIC, DECIMAL, REAL, DOUBLE, numeric…) = esquema viejo en
/// euros.
fn is_integer_type(ty: &str) -> bool {
    let t = ty.trim().to_ascii_uppercase();
    // SQLite: "INTEGER". Postgres `information_schema.data_type`: "integer", "bigint".
    t == "INTEGER" || t == "BIGINT" || t == "INT" || t == "INT8" || t == "SMALLINT"
}

/// The statement that converts one money column in place: `col = ROUND(col*100)` (euros→cents),
/// skipping NULLs. In Postgres the `NUMERIC` column stores the integer without loss; flipping the
/// column type to `INTEGER` is the job of the new schema on future installs, not of this backfill
/// (the data is already in cents, which is what the handler consumes).
fn convert_column_sql(table: &str, column: &str) -> String {
    // Table/column names come from the `MONEY_COLUMNS` constant (never external input).
    format!(
        "UPDATE {table} SET {column} = CAST(ROUND({column} * 100) AS INTEGER) \
         WHERE {column} IS NOT NULL"
    )
}

/// Detects whether the money schema is born in cents (new install) and, **only then**, seeds the
/// `money_unit=cents` marker. NEVER converts data. Meant to be called at boot
/// (`ensure_system_tables`): a NEW install gets marked automatically and the backfill will never
/// touch it, while an OLD hub in euros is **not** auto-marked (it waits for ops to run
/// `--backfill-money` explicitly, which is what converts).
///
/// Idempotent and cheap: if the marker is already there, nothing happens.
///
/// **A mixed hub (hub#1209) is not marked — and does not brick the boot either.** This runs on the
/// boot path every hub takes (`ensure_system_tables`), where an `Err` is a shop that does not open;
/// and sealing the marker would be even worse: it would freeze the anomaly forever. So it is a LOUD
/// no-op: reported to the error registry and on `stderr`, not marked, the hub keeps serving, and
/// `--backfill-money` — the one that rewrites money — flatly refuses. Same criterion as the
/// `access_email::report_unresolved` warning right below it in `ensure_system_tables`.
pub async fn seed_marker_if_cents(db: &dyn DatabaseAdapter) -> Result<bool> {
    if is_marked_cents(db).await? {
        return Ok(true);
    }
    match detect_money_unit(db).await? {
        // New install, or hub without money modules (schema "trivially" in cents): mark it so a
        // future install does not trigger a spurious conversion.
        MoneyUnit::Cents | MoneyUnit::NoMoneyColumns => {
            mark_cents(db).await?;
            Ok(true)
        }
        // Old hub in euros: do NOT mark (waits for `--backfill-money`, which is what converts).
        MoneyUnit::Euros => Ok(false),
        // Half-migrated hub: neither marked nor guessed.
        unit @ MoneyUnit::Mixed { .. } => {
            if let Some(err) = unit.refusal() {
                report_mixed(&err, "money_backfill::seed_marker_if_cents");
            }
            Ok(false)
        }
    }
}

/// Runs the idempotent backfill on the hub database.
///
/// 1. If the marker already says `cents` → no-op (returns `already_marked = true`).
/// 2. Otherwise decides by the **declared type** of **every** money column present
///    ([`detect_money_unit`]): all integer → new schema in cents → only seeds the marker
///    (`schema_already_cents = true`), without touching data.
/// 3. All `NUMERIC`/decimal → old hub in euros → converts every money column of every present
///    table (`ROUND(col*100)`) and seeds the marker, all in ONE transaction: a run that dies
///    halfway leaves nothing behind for the re-run to convert twice.
/// 4. Both kinds present (half-migrated hub) → **`Err`**
///    ([`RuntimeError::MoneyUnitAmbiguous`](crate::errors::RuntimeError::MoneyUnitAmbiguous)):
///    nothing converted, nothing marked, and reported. It is the only case in which this subcommand
///    fails, and it fails on purpose: guessing multiplies a customer's money by 100 or leaves it in
///    euros forever (hub#1209).
///
/// Idempotent: once it has run, the marker turns every re-run into a no-op.
pub async fn run(db: &dyn DatabaseAdapter) -> Result<BackfillReport> {
    let mut report = BackfillReport::default();

    // (1) Marker guard.
    if is_marked_cents(db).await? {
        report.already_marked = true;
        return Ok(report);
    }

    // (2) Schema already in cents? EVERY money column present is classified and unanimity is
    // demanded (hub#1209). If the hub disagrees with itself there is no verdict to apply: both
    // possible readings corrupt real money in opposite directions, so it is refused without
    // converting or marking, and reported for ops to look at.
    let unit = detect_money_unit(db).await?;
    if let Some(err) = unit.refusal() {
        report_mixed(&err, "money_backfill::run");
        return Err(err);
    }
    let schema_is_cents = matches!(unit, MoneyUnit::Cents | MoneyUnit::NoMoneyColumns);

    if schema_is_cents {
        // New install (or no money modules): do NOT touch data, only mark.
        report.schema_already_cents = true;
        mark_cents(db).await?;
        return Ok(report);
    }

    // (3) Old hub in euros: convert every money column present — in ONE transaction together with
    // the marker that seals it. With autocommit, a run that died halfway (a lock, a lost
    // connection) left the first tables already in cents, no marker and every column still
    // `NUMERIC`, so the re-run read the hub as euros again and multiplied those tables by 100.
    // Either everything is converted and sealed, or nothing is.
    let mut ops: Vec<(String, Params)> = Vec::new();
    for (table, columns) in MONEY_COLUMNS {
        let mut table_touched = false;
        for col in *columns {
            // Only columns that exist are converted (table/column present = module installed).
            if declared_type(db, table, col).await?.is_some() {
                ops.push((convert_column_sql(table, col), Params::new()));
                table_touched = true;
            }
        }
        if table_touched {
            report.converted_tables.push((*table).to_string());
        }
    }
    ops.push(mark_cents_op());
    let res = db.execute_tx(&ops).await?;
    // The marker upsert is the last op and always touches exactly one row.
    report.rows_updated = res.affected.saturating_sub(1);
    Ok(report)
}

/// **Read-only** check of a hub's money unit, so ops can sweep the fleet for half-migrated hubs
/// without risking anything (hub#1209).
///
/// Writes **nothing**: no conversion, no marker, not even `_hub_meta` gets created (the marker is
/// deliberately not consulted for the verdict — what is audited here is the SCHEMA, which is what
/// can disagree with itself). Safe to run against a customer's production database, including an
/// old hub in euros that has not been converted yet: `--backfill-money` is no audit because on that
/// hub it **would convert**. Delivered as `erplora-server --check-money-unit` (see
/// `crates/server/src/main.rs`).
///
/// Returns `Err` only in the mixed case, so the sweep can rely on the exit code.
pub async fn check_logged(db: &dyn DatabaseAdapter) -> Result<MoneyUnit> {
    let unit = detect_money_unit(db).await?;
    let marked = is_marked_cents_readonly(db).await?;
    match &unit {
        MoneyUnit::NoMoneyColumns => {
            eprintln!("[check-money-unit] no money tables installed — nothing to convert.");
        }
        MoneyUnit::Cents => {
            eprintln!("[check-money-unit] cents: every money column is integer.");
        }
        MoneyUnit::Euros => {
            eprintln!(
                "[check-money-unit] euros: every money column is decimal — this hub is waiting for \
                 `--backfill-money`."
            );
        }
        MoneyUnit::Mixed { cents, euros } => {
            let err = crate::errors::RuntimeError::MoneyUnitAmbiguous {
                cents: cents.join(", "),
                euros: euros.join(", "),
            };
            report_mixed(&err, "money_backfill::check_logged");
            eprintln!("[check-money-unit]   · in cents ({}): {}", cents.len(), cents.join(", "));
            eprintln!("[check-money-unit]   · in euros ({}): {}", euros.len(), euros.join(", "));
            // The marker alone does not say whether this is serious: it changes WHICH of the two
            // readings is the true one, and both really happen. It is printed next to the verdict
            // so whoever sweeps does not have to go and look it up (and does not mistake it for a
            // permission).
            if marked {
                eprintln!(
                    "[check-money-unit]   · marker `money_unit=cents`: PRESENT → two readings are \
                     possible and only the AMOUNTS in the decimal columns above tell them apart: \
                     (a) benign — the hub was converted back in the day (the conversion leaves the \
                     DATA in cents but does not change the column TYPE) and later installed a new \
                     module, born `INTEGER`; (b) SERIOUS — the hub was sealed by the hub#1209 defect \
                     and those decimal columns still hold EUROS. If the amounts are ~100 times \
                     smaller than they should be, it is (b)."
                );
            } else {
                eprintln!(
                    "[check-money-unit]   · marker `money_unit=cents`: ABSENT → half-migrated hub, \
                     not sealed. `--backfill-money` refuses (which is right): no automatic \
                     conversion can fix this without deciding column by column."
                );
            }
            return Err(err);
        }
    }
    Ok(unit)
}

/// Versión con logging amistoso para ops (la llama el subcomando del binario).
pub async fn run_logged(db: &dyn DatabaseAdapter) -> Result<BackfillReport> {
    let report = run(db).await?;
    if report.already_marked {
        eprintln!("[backfill-money] ya estaba en céntimos (marcador money_unit=cents) — no-op.");
    } else if report.schema_already_cents {
        eprintln!(
            "[backfill-money] esquema ya en céntimos (instalación nueva) — marcador sembrado, sin conversión."
        );
    } else {
        eprintln!(
            "[backfill-money] convertidas {} tablas, {} filas (euros→céntimos). Marcador sembrado. Aplicado: {}",
            report.converted_tables.len(),
            report.rows_updated,
            now_rfc3339(),
        );
        for t in &report.converted_tables {
            eprintln!("[backfill-money]   · {t}");
        }
    }
    Ok(report)
}

#[cfg(test)]
mod tests {
    use super::*;
    use erplora_db::{testutil::fresh_db, PgAdapter};

    /// Lee un valor numérico sea cual sea su representación JSON: Postgres decodifica `NUMERIC`
    /// como **string** (contrato de precisión, `pg_cell`), y los enteros/reales como número. El
    /// backfill mira las columnas `NUMERIC` (hub viejo), así que el test debe tolerar ambas.
    fn num_i64(v: &serde_json::Value) -> i64 {
        v.as_i64()
            .or_else(|| v.as_f64().map(|f| f.round() as i64))
            .or_else(|| v.as_str().and_then(|s| s.parse::<f64>().ok()).map(|f| f.round() as i64))
            .expect("valor numérico (int, real o NUMERIC-string)")
    }

    /// Crea una tabla "estilo hub viejo": columnas de dinero en `NUMERIC` con datos en euros.
    async fn old_hub_sales(db: &PgAdapter) {
        db.execute_batch(
            "CREATE TABLE sales_sale (\
                id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, \
                subtotal NUMERIC NOT NULL DEFAULT 0, \
                tax_amount NUMERIC NOT NULL DEFAULT 0, \
                discount_amount NUMERIC NOT NULL DEFAULT 0, \
                total NUMERIC NOT NULL DEFAULT 0, \
                amount_tendered NUMERIC NOT NULL DEFAULT 0, \
                change_due NUMERIC NOT NULL DEFAULT 0, \
                discount_percent NUMERIC NOT NULL DEFAULT 0);",
        )
        .await
        .unwrap();
        // Una venta de 12.34 € subtotal, 21% IVA → total 14.93 €; tendered 20, change 5.07.
        db.execute_batch(
            "INSERT INTO sales_sale \
             (id, hub_id, subtotal, tax_amount, discount_amount, total, amount_tendered, change_due, discount_percent) \
             VALUES ('s1', 'h', 12.34, 2.59, 0, 14.93, 20.00, 5.07, 10.0);",
        )
        .await
        .unwrap();
    }

    /// Crea la misma tabla "estilo hub NUEVO": columnas de dinero en `INTEGER` (céntimos).
    async fn new_hub_sales(db: &PgAdapter) {
        db.execute_batch(
            "CREATE TABLE sales_sale (\
                id TEXT PRIMARY KEY, hub_id TEXT NOT NULL, \
                subtotal INTEGER NOT NULL DEFAULT 0, \
                tax_amount INTEGER NOT NULL DEFAULT 0, \
                discount_amount INTEGER NOT NULL DEFAULT 0, \
                total INTEGER NOT NULL DEFAULT 0, \
                amount_tendered INTEGER NOT NULL DEFAULT 0, \
                change_due INTEGER NOT NULL DEFAULT 0, \
                discount_percent REAL NOT NULL DEFAULT 0);",
        )
        .await
        .unwrap();
        // Ya en céntimos: 1234, 259, 1493, 2000, 507.
        db.execute_batch(
            "INSERT INTO sales_sale \
             (id, hub_id, subtotal, tax_amount, discount_amount, total, amount_tendered, change_due, discount_percent) \
             VALUES ('s1', 'h', 1234, 259, 0, 1493, 2000, 507, 10.0);",
        )
        .await
        .unwrap();
    }

    async fn read_total(db: &PgAdapter) -> i64 {
        let res = db
            .query("SELECT total FROM sales_sale WHERE id = 's1'", &Params::new())
            .await
            .unwrap();
        num_i64(&res.rows[0]["total"])
    }
    async fn read_subtotal(db: &PgAdapter) -> i64 {
        let res = db
            .query("SELECT subtotal FROM sales_sale WHERE id = 's1'", &Params::new())
            .await
            .unwrap();
        num_i64(&res.rows[0]["subtotal"])
    }

    #[tokio::test]
    async fn old_hub_converts_euros_to_cents_then_marks() {
        let db = fresh_db().await;
        old_hub_sales(&db).await;

        let r = super::run(&db).await.unwrap();
        assert!(!r.already_marked);
        assert!(!r.schema_already_cents, "hub viejo NUMERIC debe detectarse como euros");
        assert!(r.converted_tables.contains(&"sales_sale".to_string()));

        // 12.34 € → 1234 ¢, 14.93 € → 1493 ¢, 5.07 € → 507 ¢.
        assert_eq!(read_subtotal(&db).await, 1234);
        assert_eq!(read_total(&db).await, 1493);
        let change = db
            .query("SELECT change_due FROM sales_sale WHERE id = 's1'", &Params::new())
            .await
            .unwrap();
        assert_eq!(num_i64(&change.rows[0]["change_due"]), 507);

        // discount_percent (NUMERIC, NO es dinero) NO debe convertirse → sigue 10, no 1000.
        let pct = db
            .query("SELECT discount_percent FROM sales_sale WHERE id = 's1'", &Params::new())
            .await
            .unwrap();
        // Tras la conversión el valor sigue siendo 10 (no se tocó). NUMERIC → string en Postgres.
        assert_eq!(num_i64(&pct.rows[0]["discount_percent"]), 10, "discount_percent NO es dinero, no se convierte");

        // El marcador quedó puesto.
        assert!(super::is_marked_cents(&db).await.unwrap());
    }

    #[tokio::test]
    async fn rerun_on_converted_hub_is_noop() {
        let db = fresh_db().await;
        old_hub_sales(&db).await;

        super::run(&db).await.unwrap();
        let total_after_first = read_total(&db).await; // 1493

        // Re-ejecutar NO debe re-convertir (marcador presente) → sigue 1493, no 149300.
        let r2 = super::run(&db).await.unwrap();
        assert!(r2.already_marked, "segunda corrida debe ser no-op por marcador");
        assert_eq!(r2.rows_updated, 0);
        assert_eq!(read_total(&db).await, total_after_first);
        assert_eq!(read_total(&db).await, 1493);
    }

    #[tokio::test]
    async fn new_hub_is_never_converted() {
        let db = fresh_db().await;
        new_hub_sales(&db).await;

        // Instalación nueva (esquema INTEGER): el backfill NO toca datos, solo marca.
        let r = super::run(&db).await.unwrap();
        assert!(r.schema_already_cents, "esquema INTEGER = nuevo → no convertir");
        assert!(r.converted_tables.is_empty());
        assert_eq!(r.rows_updated, 0);
        // Los datos siguen en céntimos sin tocar.
        assert_eq!(read_total(&db).await, 1493);
        assert_eq!(read_subtotal(&db).await, 1234);
        assert!(super::is_marked_cents(&db).await.unwrap());

        // Re-ejecutar también es no-op.
        let r2 = super::run(&db).await.unwrap();
        assert!(r2.already_marked);
        assert_eq!(read_total(&db).await, 1493);
    }

    #[tokio::test]
    async fn empty_db_without_money_modules_just_marks() {
        let db = fresh_db().await;
        // Ninguna tabla de dinero instalada.
        let r = super::run(&db).await.unwrap();
        assert!(r.schema_already_cents);
        assert!(r.converted_tables.is_empty());
        assert!(super::is_marked_cents(&db).await.unwrap());
    }

    #[tokio::test]
    async fn multi_table_old_hub_converts_only_present_tables() {
        let db = fresh_db().await;
        old_hub_sales(&db).await;
        // payments en euros también.
        db.execute_batch(
            "CREATE TABLE payments_payment (id TEXT PRIMARY KEY, amount NUMERIC NOT NULL DEFAULT 0);",
        )
        .await
        .unwrap();
        db.execute_batch("INSERT INTO payments_payment (id, amount) VALUES ('p1', 9.99);")
            .await
            .unwrap();

        let r = super::run(&db).await.unwrap();
        assert!(r.converted_tables.contains(&"sales_sale".to_string()));
        assert!(r.converted_tables.contains(&"payments_payment".to_string()));
        // inventory NO instalado → no aparece.
        assert!(!r.converted_tables.contains(&"inventory_product".to_string()));

        let pay = db
            .query("SELECT amount FROM payments_payment WHERE id = 'p1'", &Params::new())
            .await
            .unwrap();
        assert_eq!(num_i64(&pay.rows[0]["amount"]), 999); // 9.99 € → 999 ¢
    }
}
