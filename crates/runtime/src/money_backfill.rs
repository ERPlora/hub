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
//!  - Si no está → el backfill mira **el tipo declarado** de **todas** las columnas de dinero
//!    presentes (`information_schema.columns`, ver [`detect_money_unit`]) y exige unanimidad:
//!      - todas `INTEGER` → esquema **ya en céntimos** (instalación nueva) → solo siembra el
//!        marcador, **no toca datos**.
//!      - todas `NUMERIC`/`REAL`/decimal → esquema viejo en **euros** → convierte
//!        (`ROUND(col*100)`) y luego siembra el marcador.
//!      - **mezcla** de las dos → hub a medio migrar → **no convierte, no marca y falla de forma
//!        visible** (hub#1209). Ver [`MoneyUnit::Mixed`].
//!
//! Así un hub nuevo NUNCA se convierte (aunque aún no tenga marcador la primera vez) y un hub
//! viejo se convierte exactamente una vez. Tras sembrar el marcador, cualquier re-ejecución es
//! un no-op total.
//!
//! ## Por qué el veredicto es un CONSENSO y no la primera columna (hub#1209)
//!
//! Hasta el 28/08/2026 bastaba la **primera** columna de dinero que existiese para sentenciar al
//! hub entero, y la función salía ahí mismo. En un hub a medio migrar eso hacía que el resultado
//! dependiese del orden de una lista escrita a mano, con dos desenlaces igual de silenciosos: si
//! ganaba una entera se sembraba el marcador y los módulos en euros se quedaban en euros **para
//! siempre** (el marcador convierte toda re-ejecución en no-op); si ganaba una decimal se
//! convertían **todas** las presentes, incluidas las que ya estaban en céntimos, **multiplicándolas
//! por 100**. Reproducido contra Postgres real: 999 ¢ → 99 900 ¢. Por eso la mezcla no se resuelve
//! eligiendo una rama del `if` — se **rechaza**.
//!
//! ## Forma de entrega (ops)
//!
//! Subcomando del binario del server: `erplora-server --backfill-money` (ver
//! `crates/server/src/main.rs`). Conecta al Postgres del hub (`HUB_DATABASE_URL`), corre
//! [`run`] y sale. SEGURO de re-ejecutar.
//!
//! Y su hermano de **solo lectura**, `erplora-server --check-money-unit` ([`check_logged`],
//! hub#1209): dice en qué unidad está declarado el dinero de un hub sin escribir nada, para poder
//! barrer la flota buscando hubs a medio migrar. `--backfill-money` no vale para auditar: sobre un
//! hub viejo en euros **convertiría**.

use erplora_db::{DatabaseAdapter, Params};
use serde_json::json;

use crate::errors::Result;
use crate::registry::now_rfc3339;

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
///
/// 🔴 **«Autoritativo» aquí es una afirmación comprobada, no una promesa.** Esa misma frase
/// convivió durante meses con seis entradas cuyas tablas no existían: como `declared_type()`
/// devuelve `None` para lo que la BD no tiene, una entrada muerta se salta **en silencio** y nada
/// la delata. Quien la leía no podía saber cuáles de las 32 eran reales, y retirar una tabla en un
/// módulo obligaba a venir a leer este fichero para demostrar que no había un consumidor vivo
/// (services#67, services#69). Lo que sostiene la palabra es `tests/money_columns_inventory.rs`:
/// pone en rojo una tabla que un `contract` publicado ya retiró, una que ningún módulo crea, una
/// columna repetida (se convertiría dos veces: ×10 000) y un reordenado de la lista.
///
/// ✅ **El ORDEN ya no decide nada** (hub#1209). Hasta el 28/08/2026 el veredicto del hub entero lo
/// dictaba la **primera** columna de dinero que existiese —o sea, la posición 0 de esta lista—, así
/// que reordenar «para agrupar» movía el criterio que decide si el dinero de un cliente se
/// multiplica por 100. Hoy [`detect_money_unit`] clasifica **todas** las columnas presentes y exige
/// unanimidad; añadir, quitar o reordenar entradas ya no cambia el veredicto de una BD dada.
/// Lo que sigue importando de esta lista es **qué** hay en ella: una entrada duplicada convertiría
/// dos veces (×10 000) y una columna que falte se queda sin convertir. Eso lo fija
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

/// La unidad en la que está declarado el dinero de una BD de hub, decidida sobre **todas** las
/// columnas de [`MONEY_COLUMNS`] que existan (hub#1209).
///
/// Antes el veredicto lo daba la primera columna encontrada y la función salía ahí mismo: en un hub
/// a medio migrar eso convertía la posición en la lista en el criterio que decide si el dinero de un
/// cliente se multiplica por 100. Ahora es un consenso, y la discrepancia tiene su propio caso
/// —[`MoneyUnit::Mixed`]— en vez de resolverse adivinando.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum MoneyUnit {
    /// No hay ninguna tabla de dinero instalada: no hay nada que convertir y el hub es
    /// «trivialmente» en céntimos.
    NoMoneyColumns,
    /// Todas las columnas de dinero presentes están declaradas enteras: instalación nueva.
    Cents,
    /// Todas las columnas de dinero presentes están declaradas decimales: hub viejo en euros.
    Euros,
    /// Hay columnas de las DOS clases. No se convierte, no se marca y se reporta: las dos lecturas
    /// posibles corrompen dinero real en direcciones opuestas. Lleva los `tabla.columna` de cada
    /// lado para que ops actúe sobre ellos.
    Mixed { cents: Vec<String>, euros: Vec<String> },
}

impl MoneyUnit {
    /// El error estable que representa un hub mixto, con las columnas que discrepan. `None` para
    /// cualquier veredicto que sí se pueda aplicar.
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

/// Clasifica **todas** las columnas de dinero presentes en la BD y devuelve el veredicto del hub.
///
/// Recorre [`MONEY_COLUMNS`] entera —sin salir en la primera coincidencia— y reparte cada columna
/// que exista según su tipo declarado ([`is_integer_type`]). El resultado depende solo de lo que hay
/// en la BD, nunca del orden de la lista (hub#1209).
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

/// Reporta un hub mixto al registro de errores (severidad `unexpected`, ver
/// [`crate::error_registry::severity_of`]) y por `stderr`. Un fallo que no se ve no existe: esta es
/// la única forma en que ops se entera de que un hub se quedó a medio migrar (hub#1209).
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

/// Igual que [`is_marked_cents`] pero **sin crear nada**: si `_hub_meta` no existe todavía,
/// devuelve `false` en vez de crearla. Lo usa la auditoría de solo lectura [`check_logged`], que
/// no puede permitirse escribir en la BD de un cliente solo por mirarla (hub#1209).
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
///
/// **Un hub mixto (hub#1209) no se marca — y tampoco tumba el arranque.** Esto corre en el camino
/// de arranque que toma cualquier hub (`ensure_system_tables`), donde un `Err` es una tienda que no
/// abre; y sellar el marcador sería peor todavía: congelaría la anomalía para siempre. Así que es
/// un no-op RUIDOSO: se reporta al registro de errores y por `stderr`, no se marca, el hub sigue
/// sirviendo y `--backfill-money` —el que sí reescribe dinero— se niega en redondo. Mismo criterio
/// que el aviso de `access_email::report_unresolved` justo debajo en `ensure_system_tables`.
pub async fn seed_marker_if_cents(db: &dyn DatabaseAdapter) -> Result<bool> {
    if is_marked_cents(db).await? {
        return Ok(true);
    }
    match detect_money_unit(db).await? {
        // Instalación nueva, o hub sin módulos de dinero (esquema "trivialmente" en céntimos):
        // marcar para que un futuro install no dispare una conversión espuria.
        MoneyUnit::Cents | MoneyUnit::NoMoneyColumns => {
            mark_cents(db).await?;
            Ok(true)
        }
        // Hub viejo en euros: NO marcar (espera a `--backfill-money`, que es quien convierte).
        MoneyUnit::Euros => Ok(false),
        // Hub a medio migrar: ni se marca ni se adivina.
        unit @ MoneyUnit::Mixed { .. } => {
            if let Some(err) = unit.refusal() {
                report_mixed(&err, "money_backfill::seed_marker_if_cents");
            }
            Ok(false)
        }
    }
}

/// Ejecuta el backfill idempotente sobre la BD del hub.
///
/// 1. Si el marcador ya dice `cents` → no-op (devuelve `already_marked = true`).
/// 2. Si no, decide por **tipo declarado** de **todas** las columnas de dinero presentes
///    ([`detect_money_unit`]): si todas son enteras → esquema nuevo en céntimos → solo siembra el
///    marcador (`schema_already_cents = true`), sin tocar datos.
/// 3. Si todas son `NUMERIC`/decimal → hub viejo en euros → convierte todas las columnas de todas
///    las tablas presentes (`ROUND(col*100)`) y luego siembra el marcador.
/// 4. Si hay de las dos clases (hub a medio migrar) → **`Err`**
///    ([`RuntimeError::MoneyUnitAmbiguous`](crate::errors::RuntimeError::MoneyUnitAmbiguous)): no
///    convierte, no marca y lo reporta. Es el único caso en que este subcomando falla, y falla a
///    propósito: adivinar multiplica por 100 el dinero de un cliente o lo deja en euros para
///    siempre (hub#1209).
///
/// Idempotente: tras correr, el marcador deja cualquier re-ejecución en no-op.
pub async fn run(db: &dyn DatabaseAdapter) -> Result<BackfillReport> {
    let mut report = BackfillReport::default();

    // (1) Guarda por marcador.
    if is_marked_cents(db).await? {
        report.already_marked = true;
        return Ok(report);
    }

    // (2) ¿Esquema ya en céntimos? Se clasifican TODAS las columnas de dinero presentes y se exige
    // unanimidad (hub#1209). Si el hub disiente consigo mismo no hay veredicto que aplicar: las dos
    // lecturas posibles corrompen dinero real en direcciones opuestas, así que se rechaza sin
    // convertir ni marcar, y se reporta para que ops lo mire.
    let unit = detect_money_unit(db).await?;
    if let Some(err) = unit.refusal() {
        report_mixed(&err, "money_backfill::run");
        return Err(err);
    }
    let schema_is_cents = matches!(unit, MoneyUnit::Cents | MoneyUnit::NoMoneyColumns);

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

/// Comprobación **de solo lectura** de la unidad monetaria de un hub, para que ops pueda barrer la
/// flota buscando hubs a medio migrar sin arriesgar nada (hub#1209).
///
/// No escribe **nada**: ni convierte, ni siembra el marcador, ni siquiera crea `_hub_meta` (no mira
/// el marcador a propósito — lo que se audita aquí es el ESQUEMA, que es lo que puede discrepar
/// consigo mismo). Es seguro correrla contra la BD de un cliente en producción, incluida la de un
/// hub viejo en euros que aún no se ha convertido: `--backfill-money` no sirve para auditar porque
/// sobre ese hub **convertiría**. La entrega es `erplora-server --check-money-unit` (ver
/// `crates/server/src/main.rs`).
///
/// Devuelve `Err` solo en el caso mixto, para que el barrido pueda apoyarse en el código de salida.
pub async fn check_logged(db: &dyn DatabaseAdapter) -> Result<MoneyUnit> {
    let unit = detect_money_unit(db).await?;
    let marked = is_marked_cents_readonly(db).await?;
    match &unit {
        MoneyUnit::NoMoneyColumns => {
            eprintln!("[check-money-unit] sin tablas de dinero instaladas — nada que convertir.");
        }
        MoneyUnit::Cents => {
            eprintln!("[check-money-unit] céntimos: todas las columnas de dinero son enteras.");
        }
        MoneyUnit::Euros => {
            eprintln!(
                "[check-money-unit] euros: todas las columnas de dinero son decimales — este hub \
                 espera a `--backfill-money`."
            );
        }
        MoneyUnit::Mixed { cents, euros } => {
            let err = crate::errors::RuntimeError::MoneyUnitAmbiguous {
                cents: cents.join(", "),
                euros: euros.join(", "),
            };
            report_mixed(&err, "money_backfill::check_logged");
            eprintln!("[check-money-unit]   · en céntimos ({}): {}", cents.len(), cents.join(", "));
            eprintln!("[check-money-unit]   · en euros ({}): {}", euros.len(), euros.join(", "));
            // El marcador NO decide por sí solo si esto es grave: cambia CUÁL de las dos lecturas
            // es la cierta, y las dos existen de verdad. Se imprime junto al veredicto para que
            // quien barre no tenga que ir a buscarlo (y para que no lo confunda con un permiso).
            if marked {
                eprintln!(
                    "[check-money-unit]   · marcador `money_unit=cents`: PUESTO → dos lecturas                      posibles, y hay que distinguirlas MIRANDO LOS IMPORTES de las columnas                      decimales de arriba: (a) benigno — el hub se convirtió en su día (la                      conversión deja el DATO en céntimos pero no cambia el TIPO de la columna) y                      luego instaló un módulo nuevo, que nació `INTEGER`; (b) GRAVE — el hub se                      selló por el defecto de hub#1209 y esas columnas decimales siguen en EUROS.                      Si los importes son ~100 veces menores de lo que deberían, es (b)."
                );
            } else {
                eprintln!(
                    "[check-money-unit]   · marcador `money_unit=cents`: AUSENTE → hub a medio                      migrar y sin sellar. `--backfill-money` se niega (es lo correcto): no hay                      conversión automática que pueda arreglar esto sin decidir columna por columna."
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
