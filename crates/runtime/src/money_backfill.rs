//! Backfill **idempotente** de dinero euros→céntimos para hubs ya desplegados (ADR-0007).
//!
//! ## Por qué existe (y por qué FUERA de la cadena de migraciones)
//!
//! Cada módulo de dinero tiene su `001_init` **ya en céntimos** (`INTEGER`): una instalación
//! NUEVA nace correcta. Pero los hubs **ya desplegados** aplicaron el `001` viejo (euros,
//! `NUMERIC`) y su columna sigue en euros. El código nuevo (handlers en céntimos) multiplicaría
//! por 100 esos importes → corrupción.
//!
//! NO se puede arreglar con una migración `002` "en cadena" (`col = ROUND(col*100)`): se
//! aplicaría TAMBIÉN a las instalaciones nuevas (cuyo `001` ya dejó los datos en céntimos) →
//! **doble conversión**. Por eso el backfill vive **fuera** de `_hub_migrations`/
//! `_hub_system_migrations`: es una conversión de datos **única por BD de hub**, guardada por un
//! marcador a nivel de BD, no por la cadena de versiones de esquema.
//!
//! ## Marcador (`_hub_meta`)
//!
//! Una tabla de sistema `_hub_meta(key TEXT PRIMARY KEY, value TEXT)` con la fila
//! `('money_unit','cents')`. Es la fuente de verdad de idempotencia:
//!  - Si el marcador dice `cents` → el backfill **no hace nada** (ni en hub viejo ya convertido
//!    ni en hub nuevo ya marcado).
//!  - Si no está → el backfill mira **el tipo declarado** de las columnas de dinero
//!    (`information_schema.columns`) para distinguir:
//!      - declarado `INTEGER` → esquema **ya en céntimos** (instalación nueva) → solo siembra el
//!        marcador, **no toca datos**.
//!      - declarado `NUMERIC`/`REAL`/decimal → esquema viejo en **euros** → convierte
//!        (`ROUND(col*100)`) y luego siembra el marcador.
//!
//! Así un hub nuevo NUNCA se convierte (aunque aún no tenga marcador la primera vez) y un hub
//! viejo se convierte exactamente una vez. Tras sembrar el marcador, cualquier re-ejecución es
//! un no-op total.
//!
//! ## Forma de entrega (ops)
//!
//! Subcomando del binario del server: `erplora-server --backfill-money` (ver
//! `crates/server/src/main.rs`). Conecta al Postgres del hub (`HUB_DATABASE_URL`), corre
//! [`run`] y sale. SEGURO de re-ejecutar.

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::Result;
use crate::registry::now_rfc3339;

/// Tabla de metadatos de sistema del hub. Clave/valor, idempotente al crear.
const ENSURE_META: &str = "CREATE TABLE IF NOT EXISTS _hub_meta (\
    key TEXT PRIMARY KEY, value TEXT NOT NULL);";

/// Clave del marcador "el dinero ya está en céntimos".
const MONEY_UNIT_KEY: &str = "money_unit";
const MONEY_UNIT_CENTS: &str = "cents";

/// Inventario **autoritativo** de columnas de dinero por tabla (todas las que el `001` nuevo dejó
/// en `INTEGER` céntimos; extraído de los `001_init` de los módulos, ADR-0007 §2). NO incluye
/// tasas/porcentajes (`tax_rate`, `discount_percent`, …) ni cantidades (`quantity`) — esas son
/// `REAL` y no se multiplican por 100.
///
/// Cada entrada: `(tabla, &[columnas de dinero])`. Si la tabla no existe en la BD (módulo no
/// instalado), se ignora silenciosamente.
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
    ("kitchen_order_modifier", &["price"]),
    // kitchen_orders
    ("kitchen_orders_order", &["subtotal", "tax", "discount", "total"]),
    ("kitchen_orders_order_item", &["unit_price", "total"]),
    ("kitchen_orders_order_modifier", &["price"]),
    // orders
    ("orders_order", &["total"]),
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
    ("services_variant", &["price_adjustment"]),
    ("services_addon", &["price"]),
    ("services_package", &["fixed_price"]),
    // staff
    ("staff_member", &["hourly_rate"]),
    ("staff_service", &["custom_price"]),
    // verifactu
    ("verifactu_record", &["base_amount", "tax_amount", "total_amount"]),
];

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

/// Asegura la tabla de metadatos (idempotente).
pub async fn ensure_meta_table(db: &dyn DatabaseAdapter) -> Result<()> {
    db.execute_batch(ENSURE_META).await?;
    Ok(())
}

/// `true` si el marcador `money_unit=cents` ya está puesto.
pub async fn is_marked_cents(db: &dyn DatabaseAdapter) -> Result<bool> {
    ensure_meta_table(db).await?;
    let mut p = Params::new();
    p.insert("key".into(), json!(MONEY_UNIT_KEY));
    let res = db.query("SELECT value FROM _hub_meta WHERE key = :key", &p).await?;
    Ok(res.rows.iter().any(|r| r["value"].as_str() == Some(MONEY_UNIT_CENTS)))
}

/// Siembra el marcador `money_unit=cents` (idempotente: UPSERT por dialecto).
async fn mark_cents(db: &dyn DatabaseAdapter) -> Result<()> {
    let mut p = Params::new();
    p.insert("key".into(), json!(MONEY_UNIT_KEY));
    p.insert("value".into(), json!(MONEY_UNIT_CENTS));
    // ON CONFLICT (key) DO UPDATE; key es PK (ADR-0154: Postgres-only).
    let sql = "INSERT INTO _hub_meta (key, value) VALUES (:key, :value) \
               ON CONFLICT (key) DO UPDATE SET value = :value";
    db.execute(sql, &p).await?;
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

/// Convierte una columna de dinero en sitio: `col = ROUND(col*100)` (euros→céntimos), saltando
/// NULLs. Devuelve filas afectadas. SQLite es de tipado dinámico: tras el UPDATE el valor se
/// almacena como entero aunque la columna siga declarada `NUMERIC` (el runtime lee la clase de
/// almacenamiento, no el tipo declarado). En Postgres la columna `NUMERIC` guarda el entero sin
/// pérdida; el flip de tipo de columna a `INTEGER` lo hará el esquema nuevo en instalaciones
/// futuras, no aquí (el dato ya queda en céntimos, que es lo que consume el handler).
async fn convert_column(db: &dyn DatabaseAdapter, table: &str, column: &str) -> Result<u64> {
    // Nombres de tabla/columna vienen de la constante `MONEY_COLUMNS` (no input externo).
    let sql = format!(
        "UPDATE {table} SET {column} = CAST(ROUND({column} * 100) AS INTEGER) \
         WHERE {column} IS NOT NULL"
    );
    let res = db.execute(&sql, &Params::new()).await?;
    Ok(res.affected)
}

/// Detecta si el esquema de dinero nace en céntimos (instalación nueva) y, **solo en ese caso**,
/// siembra el marcador `money_unit=cents`. NO convierte datos nunca. Pensado para llamarse al
/// arrancar (`ensure_system_tables`): así una instalación NUEVA queda marcada automáticamente y
/// el backfill jamás la tocará, mientras que un hub VIEJO en euros **no** se auto-marca (queda a
/// la espera de que ops corra `--backfill-money` explícitamente, que es quien convierte).
///
/// Idempotente y barato: si el marcador ya está, no hace nada.
pub async fn seed_marker_if_cents(db: &dyn DatabaseAdapter) -> Result<bool> {
    if is_marked_cents(db).await? {
        return Ok(true);
    }
    // Mira el tipo declarado de la primera columna de dinero existente.
    for (table, columns) in MONEY_COLUMNS {
        for col in *columns {
            if let Some(ty) = declared_type(db, table, col).await? {
                if is_integer_type(&ty) {
                    mark_cents(db).await?;
                    return Ok(true);
                }
                // Primera columna de dinero es decimal → hub viejo en euros: NO marcar.
                return Ok(false);
            }
        }
    }
    // No hay ninguna tabla de dinero (hub sin módulos monetarios): esquema "trivialmente" en
    // céntimos → marcar para que un futuro install no dispare una conversión espuria.
    mark_cents(db).await?;
    Ok(true)
}

/// Ejecuta el backfill idempotente sobre la BD del hub.
///
/// 1. Si el marcador ya dice `cents` → no-op (devuelve `already_marked = true`).
/// 2. Si no, decide por **tipo declarado**: si las columnas de dinero ya son enteras → esquema
///    nuevo en céntimos → solo siembra el marcador (`schema_already_cents = true`), sin tocar
///    datos.
/// 3. Si son `NUMERIC`/decimal → hub viejo en euros → convierte todas las columnas de todas las
///    tablas presentes (`ROUND(col*100)`) y luego siembra el marcador.
///
/// Idempotente: tras correr, el marcador deja cualquier re-ejecución en no-op.
pub async fn run(db: &dyn DatabaseAdapter) -> Result<BackfillReport> {
    let mut report = BackfillReport::default();

    // (1) Guarda por marcador.
    if is_marked_cents(db).await? {
        report.already_marked = true;
        return Ok(report);
    }

    // (2) ¿Esquema ya en céntimos? Inspecciona el tipo declarado de la PRIMERA columna de dinero
    // que exista en la BD. Si es entero → instalación nueva; si es decimal → hub viejo.
    let mut schema_is_cents = true; // por defecto, si no hay ninguna tabla de dinero, no hay nada que convertir.
    'outer: for (table, columns) in MONEY_COLUMNS {
        for col in *columns {
            if let Some(ty) = declared_type(db, table, col).await? {
                schema_is_cents = is_integer_type(&ty);
                break 'outer; // primera columna de dinero encontrada decide.
            }
        }
    }

    if schema_is_cents {
        // Instalación nueva (o sin módulos de dinero): NO tocar datos, solo marcar.
        report.schema_already_cents = true;
        mark_cents(db).await?;
        return Ok(report);
    }

    // (3) Hub viejo en euros: convierte todas las columnas de dinero presentes.
    for (table, columns) in MONEY_COLUMNS {
        let mut table_touched = false;
        for col in *columns {
            // Solo convertimos columnas que existen (tabla/columna presente = módulo instalado).
            if declared_type(db, table, col).await?.is_some() {
                report.rows_updated += convert_column(db, table, col).await?;
                table_touched = true;
            }
        }
        if table_touched {
            report.converted_tables.push((*table).to_string());
        }
    }

    // Sella el marcador: a partir de aquí, re-ejecutar es no-op.
    mark_cents(db).await?;
    Ok(report)
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
