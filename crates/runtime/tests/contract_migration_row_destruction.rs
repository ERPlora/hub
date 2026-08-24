//! A `contract` migration may not DESTROY ROWS — it retires structure, and the runtime sets it
//! aside (hub#1145).
//!
//! The contract of hub#542, restated in ADR-0387, is that a `DROP` written by a module author never
//! destroys anything: the runtime translates it into `RENAME … TO _deprecated_…`, so the rows are
//! still there and the retirement is reversible. `Kind::Contract` used to check **no verb at all**
//! — the arm was literally `Kind::Contract => out.push(set_aside_instead_of_dropping(&statement))`
//! — and `set_aside_instead_of_dropping` only knows `DROP TABLE` and `DROP COLUMN`. So a `contract`
//! carrying `TRUNCATE` or `DELETE FROM` went through the guard untouched, ran **as written**, and
//! the rows were gone for good — while the author had every reason to believe otherwise, because
//! that is what the `kind` promises.
//!
//! These tests go through the real door (`install_from_dir` → `migrations::apply` →
//! `migration_guard::check`) against a real Postgres, the same way hub#1137's did.
use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::Runtime;
use serde_json::json;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests").join("fixture_contract1145").join(name)
}

async fn rows_in(rt: &Runtime, table: &str) -> Result<Vec<serde_json::Value>, String> {
    rt.db_for_test()
        .query(&format!("SELECT name FROM {table} ORDER BY name"), &Params::new())
        .await
        .map(|res| res.rows)
        .map_err(|e| e.to_string())
}

async fn seed(rt: &Runtime, table: &str, id: &str, name: &str, legacy: &str) {
    let mut params = Params::new();
    params.insert("id".into(), json!(id));
    params.insert("hub_id".into(), json!("h1"));
    params.insert("name".into(), json!(name));
    let sql = if table == "contract1145_thing" {
        params.insert("legacy".into(), json!(legacy));
        format!(
            "INSERT INTO {table} (id, hub_id, name, legacy) VALUES (:id, :hub_id, :name, :legacy)"
        )
    } else {
        format!("INSERT INTO {table} (id, hub_id, name) VALUES (:id, :hub_id, :name)")
    };
    rt.db_for_test()
        .execute(&sql, &params)
        .await
        .expect("sembrar la fila que la retirada NO puede destruir");
}

async fn installed_base() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture("base")).await.expect("instalar la versión 1.0.0");
    seed(&rt, "contract1145_thing", "a1", "keep me", "yes").await;
    rt
}

/// 🔴 The data-loss reproduction: a `contract` that TRUNCATEs empties the table for real.
#[tokio::test]
async fn a_contract_may_not_truncate_a_table() {
    let mut rt = installed_base().await;

    let outcome = rt.install_from_dir(&fixture("truncate")).await;

    let kept = rows_in(&rt, "contract1145_thing").await.unwrap_or_else(|e| {
        panic!(
            "la tabla tendría que seguir viva y con su fila: un `contract` retira ESTRUCTURA, y \
             vaciarla no es retirarla: {e}"
        )
    });
    assert_eq!(
        kept.len(),
        1,
        "🔴 PÉRDIDA DE DATOS: el `TRUNCATE` se ejecutó DE VERDAD y la fila sembrada ya no existe. \
         Un `contract` promete que lo destructivo se APARTA, y de las filas no hay copia ni \
         `_deprecated_*` al que volver: {kept:?}"
    );

    let error = outcome.expect_err(
        "el guard tiene que RECHAZAR la instalación: no hay traducción posible para un `TRUNCATE`, \
         así que dejarlo pasar es la única opción que pierde datos",
    );
    let message = error.to_string();
    assert!(
        message.contains("TRUNCATE"),
        "el error tiene que nombrar el verbo que lo provoca: {message}"
    );
    assert!(
        message.contains("backfill"),
        "y decir por dónde SÍ se limpian filas, o el autor no tiene salida: {message}"
    );
}

/// 🔴 The same loss with the other verb, and this one is worse: it looks surgical.
#[tokio::test]
async fn a_contract_may_not_delete_rows() {
    let mut rt = installed_base().await;

    let outcome = rt.install_from_dir(&fixture("delete")).await;

    let kept = rows_in(&rt, "contract1145_thing").await.unwrap_or_else(|e| {
        panic!("la tabla tendría que seguir viva: {e}");
    });
    assert_eq!(
        kept.len(),
        1,
        "🔴 PÉRDIDA DE DATOS: el `DELETE FROM` se ejecutó DE VERDAD sobre la BD de un cliente y la \
         fila ya no existe: {kept:?}"
    );

    let error = outcome.expect_err("el guard tiene que RECHAZAR la instalación");
    let message = error.to_string();
    assert!(
        message.contains("DELETE FROM"),
        "el error tiene que nombrar el verbo que lo provoca: {message}"
    );
    assert!(
        message.contains("backfill"),
        "y decir por dónde SÍ se limpian filas: {message}"
    );
}

/// ✅ **Control positivo**: el mismo arnés, el caso bueno, en verde. Sin esto, los dos tests de
/// arriba pasarían igual si el guard rechazase CUALQUIER `contract` — que es la forma barata de
/// «arreglar» esto rompiendo las tres migraciones `contract` ya publicadas.
#[tokio::test]
async fn a_contract_that_retires_a_table_still_sets_it_aside() {
    let mut rt = installed_base().await;

    rt.install_from_dir(&fixture("retire")).await.expect("instalar la versión 1.1.0");

    assert!(
        rows_in(&rt, "contract1145_thing").await.is_err(),
        "la tabla original deja de existir con su nombre vivo: un `contract` retira de verdad"
    );
    let kept = rows_in(&rt, "_deprecated_contract1145_thing")
        .await
        .expect("la tabla apartada tiene que existir con su fila dentro");
    assert_eq!(kept.len(), 1);
    assert_eq!(kept[0]["name"], json!("keep me"));
}

/// `DROP TABLE a, b;` produce hoy `ALTER TABLE a, RENAME TO _deprecated_a,` — SQL inválido. Falla
/// ruidosamente, que es la dirección correcta, pero el mensaje no explica nada. Se rechaza en el
/// guard, con un error que dice qué escribir.
#[tokio::test]
async fn a_contract_drops_one_table_per_statement() {
    let mut rt = installed_base().await;
    seed(&rt, "contract1145_other", "b1", "also keep me", "no").await;

    let error = rt
        .install_from_dir(&fixture("droplist"))
        .await
        .expect_err("el guard tiene que rechazar la lista de tablas en un solo `DROP TABLE`");
    let message = error.to_string();
    assert!(
        message.contains("una tabla por sentencia"),
        "el error tiene que decir qué escribir en su lugar, no reventar con un error de sintaxis \
         de Postgres: {message}"
    );

    for table in ["contract1145_thing", "contract1145_other"] {
        let kept = rows_in(&rt, table)
            .await
            .unwrap_or_else(|e| panic!("`{table}` sigue viva porque nada se llegó a aplicar: {e}"));
        assert_eq!(kept.len(), 1, "`{table}` conserva su fila");
    }
}
