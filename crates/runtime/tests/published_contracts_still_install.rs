//! 🔴 **El radio de explosión de la regla de hub#1145 es CERO, y esto lo mide.**
//!
//! Cuando se decidió que un `contract` no puede destruir filas, la comprobación de que ninguna
//! migración `contract` publicada se rompía se hizo **contra el SQL de verdad**, no contra una
//! paráfrasis: la issue hablaba de tres ficheros y para cuando se implementó eran **cuatro**
//! (`kitchen/007` entró por medio). Los ficheros viven aquí congelados como fixture porque el
//! runtime no puede leer `modules-workspace` en CI — si mañana se publica un `contract` nuevo, lo
//! que caza la divergencia es el gate del `module-toolkit`, que es la puerta de los autores.
//!
//! Es el control positivo de la regla: sin él, «rechazar cualquier `contract`» pasaría los tests
//! que dicen que un `TRUNCATE` se rechaza.
use erplora_runtime::migration_guard::{check, Kind, Plan};

/// Cada fichero, con el `module_id` y el nombre con los que el hub lo aplica de verdad.
const PUBLISHED: &[(&str, &str, &str)] = &[
    (
        "kitchen",
        "migrations/postgres/007_retire_order_modifier.sql",
        include_str!("fixtures/published_contracts/kitchen__007_retire_order_modifier.sql"),
    ),
    (
        "services",
        "migrations/postgres/009_retire_addon_tables.sql",
        include_str!("fixtures/published_contracts/services__009_retire_addon_tables.sql"),
    ),
    (
        "services",
        "migrations/postgres/010_retire_variant_table.sql",
        include_str!("fixtures/published_contracts/services__010_retire_variant_table.sql"),
    ),
    (
        "verifactu",
        "migrations/postgres/012_named_gate_constraints.sql",
        include_str!("fixtures/published_contracts/verifactu__012_named_gate_constraints.sql"),
    ),
];

#[test]
fn every_published_contract_still_passes_the_guard() {
    for (module_id, filename, sql) in PUBLISHED {
        let plan = check(module_id, filename, sql, Kind::Contract).unwrap_or_else(|e| {
            panic!(
                "🔴 `{module_id}/{filename}` está PUBLICADO y el guard lo rechaza: {e}\n\
                 Una regla nueva no puede poner en rojo lo que ya está instalado en la flota."
            )
        });
        let Plan::Rewritten(rewritten) = plan else {
            panic!("un `contract` se reescribe: {module_id}/{filename}");
        };
        // Y lo que sale sigue sin llevar un `DROP TABLE`/`DROP COLUMN` real.
        for statement in &rewritten {
            let executed = statement.to_uppercase();
            let sql_only: String = executed
                .lines()
                .filter(|line| !line.trim_start().starts_with("--"))
                .collect::<Vec<_>>()
                .join("\n");
            assert!(
                !sql_only.contains("DROP TABLE") && !sql_only.contains("DROP COLUMN"),
                "🔴 `{module_id}/{filename}` deja escapar un DROP real: {statement:?}"
            );
        }
    }
}
