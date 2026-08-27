//! `contracts/kernel/tables.snapshot` ≡ the system schema a hub really boots with —
//! ERPlora/hub#1235.
//!
//! Regression test for ERPlora/hub#1235. `hub_*` and `_*` are the RESERVED namespace: no module
//! may touch it (`migration_guard`), and the core reads it on every request. Its shape was only
//! ever written as SQL scattered across `system_migrations.rs` and five `ensure_tables`, so
//! "which columns does `hub_user` have today" had no answer short of booting a hub.
//!
//! So this test boots one. It migrates an empty Postgres schema exactly as the server does
//! (`Runtime::ensure_system_tables`) and REFLECTS the result out of `information_schema` — not out
//! of the SQL text. A snapshot parsed from the migration source would agree with a `CREATE TABLE`
//! that Postgres rejects; this one cannot.
//!
//! Needs the same Postgres every other runtime test needs (`DATABASE_URL`, ephemeral schema per
//! test — ADR-0154). Update:
//! `UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-runtime --test kernel_contract_tables`.

use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::Runtime;

#[path = "support/kernel_snapshot.rs"]
mod kernel_snapshot;

/// Reserved prefixes: `hub_*` (business tables of the core) and `_*` (machinery).
fn is_system_table(name: &str) -> bool {
    name.starts_with("hub_") || name.starts_with('_')
}

#[tokio::test]
async fn tables_snapshot_matches_the_booted_system_schema_hub1235() {
    kernel_snapshot::assert_snapshot("tables.snapshot", &generate().await);
}

async fn generate() -> String {
    let db = fresh_db().await;
    let rt = Runtime::with_hub_id(Box::new(db), "hub-contract");
    rt.ensure_system_tables()
        .await
        .expect("arrancar el esquema de sistema");

    let rows = rt
        .db_for_test()
        .query(
            "SELECT c.table_name, c.column_name, c.data_type, c.is_nullable \
             FROM information_schema.columns c \
             JOIN information_schema.tables t \
               ON t.table_schema = c.table_schema AND t.table_name = c.table_name \
             WHERE c.table_schema = current_schema() AND t.table_type = 'BASE TABLE' \
             ORDER BY c.table_name, c.column_name",
            &Params::new(),
        )
        .await
        .expect("reflejar information_schema")
        .rows;

    let mut out = String::from(
        "# Tablas de SISTEMA del hub (`hub_*`, `_*`) — reflejadas de un hub recién arrancado,\n\
         # NO editar a mano. Es el namespace RESERVADO: ninguna migración de módulo puede tocarlo.\n\
         # `UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-runtime --test kernel_contract_tables`\n\
         # Contrato del kernel: ADR «El Hub se CIERRA como KERNEL».\n",
    );
    // Una línea por COLUMNA, con la tabla delante: así cada línea es única en el fichero y el
    // fallo puede nombrar exactamente la columna que sobra o falta. Agrupar por secciones haría
    // que `label text NOT NULL` de dos tablas distintas fuese la MISMA línea, y perder una de las
    // dos no se vería en el diff de conjuntos.
    let mut current = String::new();
    let mut columns = 0usize;
    for row in &rows {
        let table = row["table_name"].as_str().expect("table_name");
        if !is_system_table(table) {
            continue;
        }
        if table != current {
            out.push('\n');
            current = table.to_string();
        }
        let column = row["column_name"].as_str().expect("column_name");
        let kind = row["data_type"].as_str().expect("data_type");
        let null = if row["is_nullable"].as_str() == Some("YES") {
            "NULL"
        } else {
            "NOT NULL"
        };
        out.push_str(&format!("{table}.{column} {kind} {null}\n"));
        columns += 1;
    }
    assert!(
        columns > 50,
        "solo se han reflejado {columns} columnas de sistema: eso no es un esquema que encogió, \
         es un arranque que no llegó a migrar"
    );
    out
}
