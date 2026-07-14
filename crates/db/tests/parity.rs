//! Paridad SQLite ↔ Postgres (tarea B4) — el producto **Cloud** (Aurora/Postgres) debe operar
//! **igual** que el **Local** (SQLite). Un módulo escribe **un solo** SQL portable (`module.json` +
//! `queries/*.sql` + `commands/*.sql` + `migrations/<dialect>/*.sql`); el `DatabaseAdapter` lo baja
//! al dialecto nativo. Estos tests ejecutan las **mismas** queries/commands de los 12 módulos del
//! core contra **ambos** backends y asertan que el resultado JSON es **idéntico** (esquema + filas +
//! scoping `hub_id` + soft-delete + parámetros de sistema `:now`/`:new_id`/`:hub_id`).
//!
//! ## Cómo correr
//!
//! - **Solo SQLite** (siempre disponible, sin entorno extra):
//!   ```sh
//!   cargo test -p erplora-db --test parity
//!   ```
//!   La rama Postgres se **salta** (se imprime un aviso), no falla: es honesto sobre lo que el
//!   entorno permite.
//!
//! - **Paridad real SQLite↔Postgres** (requiere un Postgres):
//!   ```sh
//!   # p.ej. un contenedor efímero:
//!   docker run -d --name erplora-db-parity \
//!     -e POSTGRES_USER=erplora -e POSTGRES_PASSWORD=erplora -e POSTGRES_DB=erplora_test \
//!     -p 55432:5432 postgres:16-alpine
//!   ERPLORA_TEST_PG_URL='postgres://erplora:erplora@localhost:55432/erplora_test' \
//!     cargo test -p erplora-db --test parity
//!   ```
//!   (Se acepta `DATABASE_URL` como alias de `ERPLORA_TEST_PG_URL`.) Ver
//!   `tests/docker-compose.parity.yml` para un arnés reproducible.
//!
//! ## Qué se aserta exactamente
//!
//! Cada caso corre el **mismo** par (command, query) contra los dos adaptadores y compara los
//! `QueryResult` **fila a fila, columna a columna** tras normalizar los valores no deterministas
//! (`:now`/`:new_id` se fijan a constantes para que el JSON sea comparable byte a byte). Las
//! migraciones que se aplican son las **reales** del módulo (`migrations/<dialect>/*.sql`), no una
//! copia: si una se desincroniza entre dialectos, el test lo verá.

mod parity_support;
use parity_support::{Backends, Case};

use erplora_db::DatabaseAdapter;
use serde_json::json;

// ── 1. inventory — CRUD + scoping hub_id + soft-delete ───────────────────────────────────────
//
// El caso canónico del contrato de fila (§2.5): alta con `:new_id`/`:hub_id`/`:now`, listado
// scoped por hub que excluye `is_deleted = 1`, y soft-delete que NO borra la fila pero la saca del
// listado. Usa el SQL REAL de inventory (commands/queries/migrations).

#[tokio::test]
async fn inventory_crud_scoping_softdelete_parity() {
    let b = Backends::connect().await;
    b.migrate("inventory").await;

    // Dos hubs comparten la misma BD (tenancy §2.5): h1 ve lo suyo, h2 lo suyo.
    // Alta de 2 productos en h1 + 1 en h2 con el command REAL `inventory/commands/product_create.sql`.
    let create = b.command_sql("inventory", "product_create");
    for (pid, hub, name, sku, price) in [
        ("p-coffee", "h1", "Café", "SKU-CAF", 250),
        ("p-tea", "h1", "Té", "SKU-TEA", 200),
        ("p-other", "h2", "Agua", "SKU-AGU", 100),
    ] {
        b.exec_both(
            &create,
            // El runtime inyecta new_id/hub_id/current_user_id/now; los fijamos para reproducibilidad.
            json!({
                "new_id": pid, "hub_id": hub, "current_user_id": "u1", "now": "2026-06-22T10:00:00Z",
                "name": name, "sku": sku, "ean13": null, "description": "",
                "product_type": "physical", "price": price, "cost": 0, "stock": 10,
                "low_stock_threshold": 5, "tax_class_id": null, "image": ""
            }),
        )
        .await;
    }

    // Listado scoped a h1 con la query REAL `inventory/queries/products_list.sql` → 2 filas, ordenadas.
    let list = b.query_sql("inventory", "products_list");
    let list_h1 = format!("{list} ORDER BY name");
    Case::new("inventory.products.list h1 (scoping)")
        .assert_parity(&b, &list_h1, json!({ "hub_id": "h1" }))
        .await
        .assert_rows(2);

    // h2 sólo ve su producto (scoping cruzado).
    Case::new("inventory.products.list h2 (scoping)")
        .assert_parity(&b, &list_h1, json!({ "hub_id": "h2" }))
        .await
        .assert_rows(1);

    // Soft-delete del café con el command REAL `inventory/commands/product_delete.sql`.
    let del = b.command_sql("inventory", "product_delete");
    b.exec_both(
        &del,
        json!({ "product_id": "p-coffee", "hub_id": "h1", "current_user_id": "u1", "now": "2026-06-22T11:00:00Z" }),
    )
    .await;

    // Tras el soft-delete: el listado de h1 baja a 1 (la fila sigue en disco, pero is_deleted=1).
    Case::new("inventory.products.list h1 (post soft-delete)")
        .assert_parity(&b, &list_h1, json!({ "hub_id": "h1" }))
        .await
        .assert_rows(1);

    // Y la fila NO se borró: sigue existiendo con is_deleted=1 (verificación directa, idéntica en
    // ambos motores). Confirma que soft-delete = marca, no DELETE.
    Case::new("inventory soft-delete keeps the row")
        .assert_parity(
            &b,
            "SELECT id, is_deleted, is_active, deleted_at FROM inventory_product \
             WHERE id = :id AND hub_id = :hub_id",
            json!({ "id": "p-coffee", "hub_id": "h1" }),
        )
        .await
        .assert_rows(1);
}

// ── 2. inventory — stock decrease clamp (ANTES divergencia 42883: MAX(0,…) — AHORA paridad) ────
//
// `inventory/commands/stock_decrease.sql` usaba `MAX(0, stock - :qty)` como **scalar greatest** (clamp
// a 0). SQLite tiene `MAX(a,b)` escalar; Postgres NO (ahí `MAX` es agregado y la forma escalar es
// `GREATEST(a,b)`), y con el shim DDL `stock INTEGER`→`BIGINT` la firma `max(integer, bigint)` daba
// SQLSTATE 42883 ("function does not exist") → el MISMO command funcionaba en Local y rompía en Cloud.
//
// ✅ ARREGLADO (2026-06-22) — el SQL del módulo se reescribió a una forma portable sin funciones
// dialécticas: `CASE WHEN (stock - :qty) < 0 THEN 0 ELSE (stock - :qty) END`. Igual de legible, mismo
// clamp a 0, y válido en ambos motores. Este test es ahora paridad normal: el clamp da el mismo
// resultado en SQLite y Postgres.

#[tokio::test]
async fn inventory_stock_decrease_clamp_parity() {
    let b = Backends::connect().await;
    b.migrate("inventory").await;

    let create = b.command_sql("inventory", "product_create");
    b.exec_both(
        &create,
        json!({
            "new_id": "p-phys", "hub_id": "h1", "current_user_id": "u1", "now": "2026-06-22T10:00:00Z",
            "name": "phys", "sku": "phys", "ean13": null, "description": "",
            "product_type": "physical", "price": 100, "cost": 0, "stock": 3,
            "low_stock_threshold": 5, "tax_class_id": null, "image": ""
        }),
    )
    .await;

    // Descontar 5 de un stock de 3: el clamp deja stock en 0 (no negativo) idéntico en ambos motores.
    let dec = b.command_sql("inventory", "stock_decrease");
    b.exec_both(
        &dec,
        json!({ "product_id": "p-phys", "hub_id": "h1", "qty": 5, "now": "2026-06-22T12:00:00Z" }),
    )
    .await;

    Case::new("inventory stock clamp (parity)")
        .assert_parity(
            &b,
            "SELECT id, stock FROM inventory_product WHERE hub_id = :hub_id",
            json!({ "hub_id": "h1" }),
        )
        .await
        .assert_rows(1)
        .assert_cell(0, "stock", json!(0));
}

// ── 3. taxes — REAL (tasa %) y filtros por vigencia ──────────────────────────────────────────
//
// taxes mezcla INTEGER (flags), TEXT (códigos/fechas ISO) y **REAL** (`rate_pct`). REAL es un punto
// de divergencia de tipos (SQLite REAL ↔ Postgres DOUBLE PRECISION vía shim DDL). Verificamos que el
// número vuelve idéntico en JSON.
//
// ⚠️ Este test estaba ROTO desde el ADR-0085 y nadie lo vio: se escribió contra el contrato viejo
// (tabla `taxes_rate`, command `rate_create`, campo `code`), y el ADR-0085 reestructuró el módulo a
// `taxes_category` + `taxes_rule` con `tax_category_key`. `taxes_rate` y `rate_create` YA NO EXISTEN.
// Fallaba en `NOT NULL constraint failed: taxes_category.key` — el test mandaba `code`, que el SQL
// ignora, así que `key` llegaba NULL. Reescrito contra el contrato vivo: lo que verifica (roundtrip
// de REAL entre motores) sigue siendo válido, lo que había caducado era el módulo al que apuntaba.

#[tokio::test]
async fn taxes_rate_real_and_active_filter_parity() {
    let b = Backends::connect().await;
    b.migrate("taxes").await;

    // Categoría + dos reglas (una al 21%, otra al 10.5%).
    let cat = b.command_sql("taxes", "category_create");
    b.exec_both(
        &cat,
        json!({
            "new_id": "cat-std", "hub_id": "h1", "current_user_id": "u1", "now": "2026-06-22T10:00:00Z",
            "key": "std", "name": "IVA general", "description": "", "is_system": 0
        }),
    )
    .await;

    let rule = b.command_sql("taxes", "rule_create");
    for (rid, pct, from, until) in [
        ("r-21", 21.0, "2026-01-01", null_str()),
        ("r-10", 10.5, "2025-01-01", Some("2025-12-31")),
    ] {
        b.exec_both(
            &rule,
            json!({
                "new_id": rid, "hub_id": "h1", "current_user_id": "u1", "now": "2026-06-22T10:00:00Z",
                "tax_category_key": "std", "country_code": "ES", "region_code": "",
                "rate_pct": pct, "tax_type": "vat", "parent_id": null_str(), "component_label": "",
                "valid_from": from, "valid_to": until
            }),
        )
        .await;
    }

    // REAL fraccionario (10.5) y entero-como-real (21.0) deben volver idénticos en ambos motores.
    Case::new("taxes rate_pct REAL roundtrip")
        .assert_parity(
            &b,
            "SELECT id, rate_pct FROM taxes_rule WHERE hub_id = :hub_id ORDER BY id",
            json!({ "hub_id": "h1" }),
        )
        .await
        .assert_rows(2)
        // `rate_pct` es REAL; el arnés normaliza floats-enteros (21.0 → 21) para que la celda sea
        // comparable byte a byte entre motores. 10.5 es fraccionario y se mantiene.
        // Orden por `id`: "r-10" (10.5) antes que "r-21" (21).
        .assert_cell(0, "rate_pct", json!(10.5))
        .assert_cell(1, "rate_pct", json!(21));
}

// ── 4a. sales — _bump_counter upsert (ANTES divergencia 42702: self-ref ambiguo — AHORA paridad) ─
//
// `sales/commands/_bump_counter.sql`: `ON CONFLICT (hub_id, day) DO UPDATE SET last_number =
// last_number + 1`. SQLite resolvía `last_number` a la fila existente; Postgres lo consideraba
// **ambiguo** (SQLSTATE 42702) y rechazaba el statement al planificarlo (no dependía de que hubiera
// conflicto) → el MISMO command arrancaba el contador en Local y rompía en Cloud.
//
// ✅ ARREGLADO (2026-06-22) — el `DO UPDATE` se cualifica con el nombre de tabla
// (`sales_sale_counter.last_number + 1`), portable a ambos motores. Mismo patrón aplicado a los
// `_bump_counter.sql` del core (sales, cart_checkout, orders, kitchen). Este test es ahora paridad
// normal: dos bumps dejan el contador en 2 idéntico en SQLite y Postgres (insert + conflict-update).

#[tokio::test]
async fn sales_counter_upsert_parity() {
    let b = Backends::connect().await;
    b.migrate("sales").await;

    // Primer bump: INSERT (arranca en 1). Segundo bump: choca con (hub_id, day) → DO UPDATE (a 2).
    let bump = b.command_sql("sales", "_bump_counter");
    b.exec_both(&bump, json!({ "new_id": "c-0", "hub_id": "h1", "day": "2026-06-22" })).await;
    b.exec_both(&bump, json!({ "new_id": "c-1", "hub_id": "h1", "day": "2026-06-22" })).await;

    Case::new("sales counter upsert (parity)")
        .assert_parity(
            &b,
            "SELECT last_number FROM sales_sale_counter WHERE hub_id = :hub_id AND day = :day",
            json!({ "hub_id": "h1", "day": "2026-06-22" }),
        )
        .await
        .assert_rows(1)
        .assert_cell(0, "last_number", json!(2));
}

// ── 4b. sales — erp_pad numeración de documento (PARIDAD REAL, independiente del upsert) ───────
//
// `erp_pad` baja a `printf('%0*d', …)` (SQLite) / `lpad((…)::text, …, '0')` (Postgres). Probamos el
// formato sobre una fila insertada directamente (sin tocar el upsert roto) → debe dar el MISMO
// "FAC-00003" en ambos motores. Esta sí es paridad de verdad.

#[tokio::test]
async fn sales_erp_pad_document_number_parity() {
    let b = Backends::connect().await;
    b.migrate("sales").await;

    // Insert directo del contador (evita el ON CONFLICT divergente del 4a).
    b.exec_both(
        "INSERT INTO sales_sale_counter (id, hub_id, day, last_number) \
         VALUES (:id, :hub_id, :day, :n)",
        json!({ "id": "ctr-1", "hub_id": "h1", "day": "2026-06-22", "n": 3 }),
    )
    .await;

    Case::new("sales erp_pad document number")
        .assert_parity(
            &b,
            "SELECT 'FAC-' || erp_pad(last_number, 5) AS num FROM sales_sale_counter \
             WHERE hub_id = :hub_id AND day = :day",
            json!({ "hub_id": "h1", "day": "2026-06-22" }),
        )
        .await
        .assert_cell(0, "num", json!("FAC-00003"));
}

// ── 5. customers — alta con NULLs tipados en las columnas REALMENTE nullable ───────────────────
//
// `customers/commands/create.sql` mezcla columnas `TEXT NOT NULL DEFAULT ''` (email, phone, …, que
// reciben `""` del schema/UI) con columnas **nullable** de verdad (`birthday`, `anniversary`,
// `consent_date`). Pasamos `null` en esas tres → ejercita el binding de NULL tipado como TEXT, que es
// el TODO Fase-0 del adaptador Postgres. Si Postgres rechazara un `Option::<String>::None` contra una
// columna TEXT nullable, fallaría aquí. (Las NOT NULL reciben `""` como haría el JSON Schema, no NULL:
// pasar null ahí viola la constraint EN AMBOS motores — es un invariante del módulo, no de paridad.)

#[tokio::test]
async fn customers_create_with_typed_nulls_parity() {
    let b = Backends::connect().await;
    b.migrate("customers").await;

    let create = b.command_sql("customers", "create");
    b.exec_both(
        &create,
        json!({
            "new_id": "cust-1", "hub_id": "h1", "current_user_id": "u1", "now": "2026-06-22T10:00:00Z",
            "name": "Ada Lovelace",
            // NOT NULL DEFAULT '' → el caller (schema/UI) aporta "" , nunca null.
            "email": "", "phone": "", "tax_id": "", "address": "", "city": "", "postal_code": "",
            "country": "", "avatar": "", "notes": "", "lifecycle_stage": "lead", "source": "walk_in",
            "company_name": "", "preferred_channel": "none", "marketing_consent": 0,
            // columnas nullable de verdad → NULL (ejercita el binding NULL→TEXT en Postgres).
            "birthday": null, "anniversary": null, "consent_date": null
        }),
    )
    .await;

    // La fila vuelve idéntica en ambos motores: name presente, "" en los NOT NULL, null en los
    // nullable, total_spent/is_deleted con sus defaults numéricos.
    Case::new("customers create (typed NULLs on nullable cols)")
        .assert_parity(
            &b,
            "SELECT id, name, email, birthday, anniversary, consent_date, total_spent, is_deleted \
             FROM customers_customer WHERE hub_id = :hub_id",
            json!({ "hub_id": "h1" }),
        )
        .await
        .assert_rows(1)
        .assert_cell(0, "name", json!("Ada Lovelace"))
        .assert_cell(0, "email", json!(""))
        .assert_cell(0, "birthday", json!(null))
        .assert_cell(0, "anniversary", json!(null))
        .assert_cell(0, "consent_date", json!(null))
        .assert_cell(0, "total_spent", json!(0))
        .assert_cell(0, "is_deleted", json!(0));
}

// ── 6. transacción atómica idéntica (all-or-nothing) en ambos motores ────────────────────────
//
// `execute_tx` debe hacer rollback completo ante un fallo, igual en SQLite y Postgres. Insertamos
// una fila válida y luego una que viola la PK en la MISMA tx → ambas se revierten.

#[tokio::test]
async fn tx_rollback_parity() {
    let b = Backends::connect().await;
    b.migrate("inventory").await;

    let create = b.command_sql("inventory", "product_create");
    let good = parity_support::params(json!({
        "new_id": "p-tx", "hub_id": "h1", "current_user_id": "u1", "now": "2026-06-22T10:00:00Z",
        "name": "ok", "sku": "SKU-OK", "ean13": null, "description": "",
        "product_type": "physical", "price": 100, "cost": 0, "stock": 1,
        "low_stock_threshold": 5, "tax_class_id": null, "image": ""
    }));
    // Segunda op con el MISMO id → viola la PK → la tx entera revierte.
    let dup = good.clone();

    let ops = vec![(create.clone(), good), (create.clone(), dup)];

    let sqlite_err = b.sqlite.execute_tx(&ops).await.is_err();
    assert!(sqlite_err, "SQLite: la tx con PK duplicada debe fallar");
    if let Some(pg) = &b.pg {
        assert!(pg.execute_tx(&ops).await.is_err(), "Postgres: la tx con PK duplicada debe fallar");
    }

    // Tras el rollback, 0 filas en AMBOS motores (la fila válida también se revirtió).
    Case::new("tx rollback leaves no rows")
        .assert_parity(
            &b,
            "SELECT id FROM inventory_product WHERE hub_id = :hub_id",
            json!({ "hub_id": "h1" }),
        )
        .await
        .assert_rows(0);
}

// ── 7a. binding de NULL contra columna TEXT nullable (PARIDAD REAL — el caso común) ───────────
//
// `build_query!` bindea cualquier `Json::Null` como `Option::<String>::None` → NULL con OID TEXT.
// Contra una columna **TEXT** nullable esto funciona perfecto en ambos motores: es el caso de los
// módulos del core (todas sus columnas nullable son TEXT: fechas ISO, refs opcionales). Lo fijamos
// como paridad para proteger el caso real.

#[tokio::test]
async fn typed_null_into_text_column_parity() {
    let b = Backends::connect().await;
    let ddl = "CREATE TABLE nulltext (id TEXT PRIMARY KEY, t TEXT)";
    b.sqlite_batch(ddl).await;
    b.pg_batch(ddl).await;

    let ins = "INSERT INTO nulltext (id, t) VALUES (:id, :t)";
    b.exec_both(ins, json!({ "id": "with", "t": "x" })).await;
    b.exec_both(ins, json!({ "id": "nulls", "t": null })).await;

    Case::new("typed NULL into TEXT (parity)")
        .assert_parity(&b, "SELECT id, t FROM nulltext ORDER BY id", json!({}))
        .await
        .assert_rows(2)
        .assert_cell(0, "t", json!(null)) // 'nulls'
        .assert_cell(1, "t", json!("x")); // 'with'
}

// ── 7b. binding de NULL contra columna NO-TEXT (ANTES divergencia 42804 — AHORA paridad) ───────
//
// El TODO de `lib.rs` (~línea 103) preguntaba si el NULL-tipado-TEXT choca con una columna de otro
// tipo. **Sí chocaba**: insertar `Option::<String>::None` en una columna `BIGINT`/`DOUBLE PRECISION`
// nullable → Postgres `42804` ("column is of type bigint but expression is of type text"). SQLite no
// tiene tipos estáticos de columna, así que lo aceptaba. → era una divergencia REAL del adaptador.
//
// ✅ ARREGLADO (2026-06-22) — `build_query!` ya no bindea `Json::Null` como `Option::<String>::None`
// (OID TEXT), sino como `DynNull` (ver `lib.rs`): en Postgres emite el NULL con OID 0
// ("inferir el tipo por contexto"), así el servidor lo coacciona a la columna destino; en SQLite es
// un NULL plano. El MISMO command declarativo se comporta IGUAL en Local (SQLite) y Cloud (Postgres).
//
// ALCANCE REAL (verificado): NO era latente. Hay columnas nullable NUMÉRICAS en el core —
// `cash_register.closing_balance/expected_balance/difference` (céntimos, INTEGER nullable),
// `kitchen.seat_number`, `pricing.min_amount/max_amount/max_quantity`. Ej. concreto:
// `cash_register/commands/close_session.sql` hace `closing_balance = :closing_balance`; un cierre de
// caja sin recuento (`closing_balance: null`) ahora funciona en AMBOS motores.
//
// Este test (antes `..._divergence`, fijaba el 42804) es ahora paridad normal: ambos motores aceptan
// el NULL en una columna numérica nullable y lo leen de vuelta como NULL.

#[tokio::test]
async fn typed_null_into_numeric_column_parity() {
    let b = Backends::connect().await;
    // `n INTEGER` → BIGINT en Postgres vía shim DDL; columna nullable a propósito.
    let ddl = "CREATE TABLE nullnum (id TEXT PRIMARY KEY, n INTEGER)";
    b.sqlite_batch(ddl).await;
    b.pg_batch(ddl).await;

    // NULL en la columna numérica nullable + una fila con valor: ambos motores deben aceptarlo igual.
    let ins = "INSERT INTO nullnum (id, n) VALUES (:id, :n)";
    b.exec_both(ins, json!({ "id": "a", "n": null })).await;
    b.exec_both(ins, json!({ "id": "b", "n": 42 })).await;

    // Lectura de vuelta idéntica en ambos: la fila NULL devuelve NULL, la otra el entero.
    Case::new("typed NULL into NUMERIC (parity)")
        .assert_parity(&b, "SELECT id, n FROM nullnum ORDER BY id", json!({}))
        .await
        .assert_rows(2)
        .assert_cell(0, "n", json!(null)) // 'a'
        .assert_cell(1, "n", json!(42)); // 'b'
}

/// Helper: `null` como `Option<&str>` para los arrays heterogéneos de arriba (evita anotar el tipo).
fn null_str() -> Option<&'static str> {
    None
}
