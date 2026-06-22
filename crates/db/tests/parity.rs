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

// ── 2. inventory — stock decrease (DIVERGENCIA CONOCIDA: MAX(0,…) no es portable) ─────────────
//
// `inventory/commands/stock_decrease.sql` usa `MAX(0, stock - :qty)` como **scalar greatest** (clamp
// a 0). SQLite tiene `MAX(a,b)` escalar; Postgres NO: ahí `MAX` es un agregado y la forma escalar se
// llama `GREATEST(a,b)`. Además el shim DDL mapea `stock INTEGER`→`BIGINT`, así que la firma queda
// `max(integer, bigint)` → SQLSTATE 42883 ("function does not exist").
//
// ⚠️ [REVISAR HUMANO] — semántica de tipos/funciones, NO un binding trivial. Opciones (decisión del
// humano): (a) añadir una función-puente `erp_greatest(a,b)`/`erp_least(a,b)` al shim
// (SQLite→`MAX/MIN`, Postgres→`GREATEST/LEAST`) y migrar los módulos a ella; o (b) reescribir
// `MAX(0, x)`→`GREATEST(0, x)` en `shim_functions` cuando el dialecto es Postgres. Afecta:
// inventory/commands/stock_decrease.sql y stock_adjust.sql (grep `MAX(0`).
//
// Este test FIJA la divergencia (SQLite ok, Postgres 42883). Cuando el humano la arregle, saltará y
// habrá que convertirlo en un `assert_parity` normal (la forma correcta del assert de paridad está
// comentada abajo, lista para reactivar).

#[tokio::test]
async fn inventory_stock_decrease_max_divergence() {
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

    let dec = b.command_sql("inventory", "stock_decrease");
    // Descontar 5 de un stock de 3: en SQLite hace clamp a 0; en Postgres falla por `max(int,bigint)`.
    b.exec_known_divergence(
        &dec,
        json!({ "product_id": "p-phys", "hub_id": "h1", "qty": 5, "now": "2026-06-22T12:00:00Z" }),
        "42883",
    )
    .await;

    // FUTURO (cuando MAX/GREATEST sea portable) — paridad del clamp y del filtro service:
    //   b.exec_both(&dec, json!({ "product_id":"p-phys","hub_id":"h1","qty":5,"now":"…" })).await;
    //   Case::new("inventory stock clamp")
    //       .assert_parity(&b, "SELECT id, stock FROM inventory_product WHERE hub_id = :hub_id", …)
    //       .await.assert_cell(0, "stock", json!(0));
}

// ── 3. taxes — REAL (tasa %) y filtros por vigencia ──────────────────────────────────────────
//
// taxes mezcla INTEGER (flags), TEXT (códigos/fechas ISO) y **REAL** (`rate_pct`). REAL es un punto
// de divergencia de tipos (SQLite REAL ↔ Postgres DOUBLE PRECISION vía shim DDL). Verificamos que el
// número vuelve idéntico en JSON.

#[tokio::test]
async fn taxes_rate_real_and_active_filter_parity() {
    let b = Backends::connect().await;
    b.migrate("taxes").await;

    // Categoría + dos tipos (uno activo al 21%, otro inactivo al 10%).
    let cat = b.command_sql("taxes", "category_create");
    b.exec_both(
        &cat,
        json!({
            "new_id": "cat-std", "hub_id": "h1", "current_user_id": "u1", "now": "2026-06-22T10:00:00Z",
            "code": "STD", "name": "IVA general", "description": ""
        }),
    )
    .await;

    let rate = b.command_sql("taxes", "rate_create");
    for (rid, code, pct, from, until) in [
        ("r-21", "IVA21", 21.0, "2026-01-01", null_str()),
        ("r-10", "IVA10", 10.5, "2025-01-01", Some("2025-12-31")),
    ] {
        b.exec_both(
            &rate,
            json!({
                "new_id": rid, "hub_id": "h1", "current_user_id": "u1", "now": "2026-06-22T10:00:00Z",
                "code": code, "name": code, "category_id": "cat-std",
                "country_code": "ES", "region_code": "", "rate_pct": pct, "tax_type": "vat",
                "applies_from": from, "applies_until": until
            }),
        )
        .await;
    }

    // REAL fraccionario (10.5) y entero-como-real (21.0) deben volver idénticos en ambos motores.
    Case::new("taxes rate_pct REAL roundtrip")
        .assert_parity(
            &b,
            "SELECT code, rate_pct FROM taxes_rate WHERE hub_id = :hub_id ORDER BY code",
            json!({ "hub_id": "h1" }),
        )
        .await
        .assert_rows(2)
        // `rate_pct` es REAL; el arnés normaliza floats-enteros (21.0 → 21) para que la celda sea
        // comparable byte a byte entre motores. 10.5 es fraccionario y se mantiene.
        .assert_cell(0, "rate_pct", json!(10.5))
        .assert_cell(1, "rate_pct", json!(21));
}

// ── 4a. sales — _bump_counter upsert (DIVERGENCIA CONOCIDA: self-ref ambiguo en Postgres) ─────
//
// `sales/commands/_bump_counter.sql`: `ON CONFLICT (hub_id, day) DO UPDATE SET last_number =
// last_number + 1`. SQLite resuelve `last_number` a la fila existente; Postgres lo considera
// **ambiguo** (SQLSTATE 42702) — en el `DO UPDATE` hay que cualificar (`sales_sale_counter.last_number`)
// o usar `EXCLUDED`. Es el mismo patrón en 9 módulos (grep `DO UPDATE SET last_number = last_number`),
// 3 de ellos del core (sales, cart_checkout, orders, kitchen).
//
// ⚠️ [REVISAR HUMANO] — semántica de upsert, NO un binding. Opciones: (a) cualificar el self-ref con
// el nombre de tabla en los `_bump_counter.sql` (portable a ambos); o (b) que el adaptador reescriba
// el self-ref no cualificado del `DO UPDATE` para Postgres (más frágil). Recomendado: (a), es un
// cambio mecánico de SQL del módulo.

#[tokio::test]
async fn sales_counter_upsert_divergence() {
    let b = Backends::connect().await;
    b.migrate("sales").await;

    let bump = b.command_sql("sales", "_bump_counter");
    // Postgres rechaza el statement al PLANIFICARLO (el self-ref ambiguo del `DO UPDATE` no depende
    // de que haya conflicto): falla ya en el primer INSERT. SQLite lo acepta y arranca el contador.
    b.exec_known_divergence(
        &bump,
        json!({ "new_id": "c-0", "hub_id": "h1", "day": "2026-06-22" }),
        "42702",
    )
    .await;
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

// ── 7b. binding de NULL contra columna NO-TEXT (DIVERGENCIA CONOCIDA — el TODO Fase-0 era REAL) ─
//
// El TODO de `lib.rs` (~línea 103) preguntaba si el NULL-tipado-TEXT choca con una columna de otro
// tipo. **Sí choca**: insertar `Option::<String>::None` en una columna `BIGINT`/`DOUBLE PRECISION`
// nullable → Postgres `42804` ("column is of type bigint but expression is of type text"). SQLite no
// tiene tipos estáticos de columna, así que lo acepta. → Divergencia REAL del adaptador.
//
// ⚠️ [REVISAR HUMANO] — semántica de tipos del adaptador (carga pesada, NO un binding trivial). El
// arreglo correcto es que `build_query!`, ante un `Json::Null`, NO fije el OID a TEXT sino que envíe
// un NULL de tipo **inferido por contexto** (en Postgres, OID `unknown`/705) para que el motor lo
// coaccione a la columna destino. sqlx 0.9 no lo expone vía `.bind()` directo → requiere un wrapper
// `Encode` propio (o conocer el tipo de la columna). Es decisión del humano (toca el core del
// adaptador).
//
// ⚠️ ALCANCE REAL (verificado): NO es latente. Hay columnas nullable NUMÉRICAS en el core —
// `cash_register.closing_balance/expected_balance/difference` (céntimos, INTEGER nullable),
// `kitchen.seat_number`, `pricing.min_amount/max_amount/max_quantity`. Ej. concreto:
// `cash_register/commands/close_session.sql` hace `closing_balance = :closing_balance`; si un caller
// cierra caja sin recuento (`closing_balance: null`), Postgres dará 42804 y SQLite no → el MISMO
// command funciona en Local y rompe en Cloud. Es un bug alcanzable hoy, no teórico.
//
// Este test FIJA la divergencia (SQLite ok, Postgres 42804). Cuando el humano arregle el binding,
// saltará → conviértelo en `typed_null_into_text_column_parity` extendido a columnas numéricas.

#[tokio::test]
async fn typed_null_into_non_text_column_divergence() {
    let b = Backends::connect().await;
    // `n INTEGER` → BIGINT en Postgres vía shim DDL; columna nullable a propósito.
    let ddl = "CREATE TABLE nullnum (id TEXT PRIMARY KEY, n INTEGER)";
    b.sqlite_batch(ddl).await;
    b.pg_batch(ddl).await;

    // NULL en la columna numérica nullable: SQLite ok; Postgres rechaza por mismatch text↔bigint.
    b.exec_known_divergence(
        "INSERT INTO nullnum (id, n) VALUES (:id, :n)",
        json!({ "id": "a", "n": null }),
        "42804",
    )
    .await;
}

/// Helper: `null` como `Option<&str>` para los arrays heterogéneos de arriba (evita anotar el tipo).
fn null_str() -> Option<&'static str> {
    None
}
