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

/// The file is ordered by BYTES, whatever order Postgres hands the rows back in: `ORDER BY` on
/// text follows the collation of the database it runs on (`en_US` and `C` disagree on where `_`
/// goes), and a snapshot that moved lines between two machines would fail naming nothing
/// (review of hub#1252).
#[test]
fn the_file_is_sorted_by_bytes_whatever_order_postgres_returns_hub1235() {
    let column = |table: &str| {
        (
            table.to_string(),
            "id".to_string(),
            "text".to_string(),
            "NOT NULL".to_string(),
        )
    };
    let sorted = vec![
        column("_flow_run_steps"),
        column("_flow_runs"),
        column("hub_user"),
    ];
    let mut scrambled = sorted.clone();
    scrambled.reverse();
    assert_eq!(render(&sorted), render(&scrambled));
    let text = render(&scrambled);
    assert!(
        text.find("_flow_run_steps.") < text.find("_flow_runs."),
        "`_` tiene que ordenar antes que `s` (orden de bytes), y no lo hace:\n{text}"
    );
    assert!(
        text.find("_flow_runs.") < text.find("hub_user."),
        "`_*` tiene que ir antes que `hub_*` (orden de bytes), y no lo hace:\n{text}"
    );
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

    let mut columns: Vec<(String, String, String, String)> = rows
        .iter()
        .filter(|row| is_system_table(row["table_name"].as_str().expect("table_name")))
        .map(|row| {
            let null = if row["is_nullable"].as_str() == Some("YES") {
                "NULL"
            } else {
                "NOT NULL"
            };
            (
                row["table_name"].as_str().expect("table_name").to_string(),
                row["column_name"]
                    .as_str()
                    .expect("column_name")
                    .to_string(),
                row["data_type"].as_str().expect("data_type").to_string(),
                null.to_string(),
            )
        })
        .collect();
    assert!(
        columns.len() > 50,
        "solo se han reflejado {} columnas de sistema: eso no es un esquema que encogió, \
         es un arranque que no llegó a migrar",
        columns.len()
    );
    // Byte order, decided HERE and not by the `ORDER BY`: the collation of the database the rows
    // come from must not be able to move a line of this file.
    columns.sort();
    render(&columns)
}

/// One line per column `(table, column, type, nullability)`, tables separated by a blank line.
///
/// Byte-sorted before writing, whatever order the caller hands the columns in. The table goes IN
/// FRONT of every line so each line is unique in the file and a failure can name the exact column
/// that is missing or new: grouped by section, `label text NOT NULL` of two different tables would
/// be the SAME line and losing one of them would not show in a set difference.
fn render(columns: &[(String, String, String, String)]) -> String {
    let mut sorted: Vec<&(String, String, String, String)> = columns.iter().collect();
    sorted.sort();
    let mut out = String::from(
        "# Tablas de SISTEMA del hub (`hub_*`, `_*`) — reflejadas de un hub recién arrancado,\n\
         # NO editar a mano. Es el namespace RESERVADO: ninguna migración de módulo puede tocarlo.\n\
         # `UPDATE_KERNEL_CONTRACT=1 cargo test -p erplora-runtime --test kernel_contract_tables`\n\
         # Contrato del kernel: ADR «El Hub se CIERRA como KERNEL».\n",
    );
    let mut current = "";
    for (table, column, kind, null) in sorted {
        if table != current {
            out.push('\n');
            current = table;
        }
        out.push_str(&format!("{table}.{column} {kind} {null}\n"));
    }
    out
}
