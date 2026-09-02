//! Dos arranques del MISMO hub contra la MISMA base, a la vez (hub#539).
//!
//! Es el caso normal de cada actualización en cuanto se active `order: start-first`
//! (ADR-0269/saas#1249), no una rareza: la tarea nueva arranca **mientras la vieja sigue
//! sirviendo**, y las dos corren `ensure_system_tables()` entero.
//!
//! Sin el lock, las dos leen el mismo `max_applied_version` y aplican la misma migración a la vez.
//! Lo que pasa entonces depende de la migración —`CREATE TABLE` sin `IF NOT EXISTS` da 42P07, un
//! `ALTER` deja el esquema a medias, el `INSERT` de control choca contra la PK— y **no es
//! determinista**, que es lo peor de todo: falla una vez de cada tantas, en producción, durante una
//! actualización.
//!
//! Estos tests fallan si se quita el lock.

use erplora_db::testutil::two_adapters_sharing_a_schema;
use erplora_db::{DatabaseAdapter, Params};
use erplora_runtime::Runtime;

const HUB: &str = "hub-concurrent";

async fn count(db: &dyn DatabaseAdapter, sql: &str) -> i64 {
    let result = db
        .query(sql, &Params::new())
        .await
        .expect("consulta de control");
    let row = &result.rows[0];
    row["n"]
        .as_i64()
        .or_else(|| row["n"].as_str()?.parse().ok())
        .expect("un número")
}

#[tokio::test]
async fn two_boots_at_once_leave_a_sane_schema_and_apply_each_migration_once() {
    let (first_db, second_db) = two_adapters_sharing_a_schema().await;

    let first = Runtime::with_hub_id(Box::new(first_db), HUB);
    let second = Runtime::with_hub_id(Box::new(second_db), HUB);

    // Los dos a la vez, como el solape.
    let (a, b) = tokio::join!(first.ensure_system_tables(), second.ensure_system_tables());

    a.expect("el primer arranque migra");
    b.expect("el segundo espera, entra, y encuentra el trabajo hecho — no revienta");

    // Ninguna migración registrada dos veces: es lo que rompería la PK de control y, antes de eso,
    // lo que significaría haber ejecutado el mismo DDL dos veces.
    let duplicated = count(
        first.db(),
        "SELECT COUNT(*) AS n FROM (\
           SELECT version FROM _hub_system_migrations GROUP BY version HAVING COUNT(*) > 1\
         ) d",
    )
    .await;
    assert_eq!(
        duplicated, 0,
        "hay migraciones de sistema registradas más de una vez"
    );

    // Y el esquema quedó completo: las tablas del baseline existen de verdad.
    for table in ["hub_module", "_hub_system_migrations", "_event_outbox"] {
        let exists = count(
            first.db(),
            &format!(
                "SELECT COUNT(*) AS n FROM information_schema.tables \
                 WHERE table_name = '{table}' AND table_schema = current_schema()"
            ),
        )
        .await;
        assert_eq!(
            exists, 1,
            "falta la tabla `{table}` tras dos arranques simultáneos"
        );
    }
}

/// Y con **cuatro** — un reschedule de Swarm encima de una actualización no es imposible.
#[tokio::test]
async fn four_boots_at_once_still_end_up_with_one_schema() {
    let db = erplora_db::testutil::TestDb::new().await;
    let mut runtimes = Vec::new();
    for _ in 0..4 {
        runtimes.push(Runtime::with_hub_id(Box::new(db.adapter().await), HUB));
    }

    let (a, b, c, d) = tokio::join!(
        runtimes[0].ensure_system_tables(),
        runtimes[1].ensure_system_tables(),
        runtimes[2].ensure_system_tables(),
        runtimes[3].ensure_system_tables(),
    );
    for (i, outcome) in [a, b, c, d].iter().enumerate() {
        assert!(outcome.is_ok(), "el arranque {i} falló: {outcome:?}");
    }

    let duplicated = count(
        runtimes[0].db(),
        "SELECT COUNT(*) AS n FROM (\
           SELECT version FROM _hub_system_migrations GROUP BY version HAVING COUNT(*) > 1\
         ) d",
    )
    .await;
    assert_eq!(duplicated, 0);
}
