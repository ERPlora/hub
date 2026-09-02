//! La lista efectiva de migraciones por dialecto es la **unión** `manifest ∪
//! migrations/<dialecto>/*.sql` del paquete, ordenada por nombre (decisión Ioan 2026-07-05,
//! opción A2 — bug "instalado pero muerto" en hubs Cloud: 16 manifests omiten
//! `migrations.postgres` aunque el `.sql` viaja en el zip, e `invoice` lista 002 sin 001).
//!
//! Se prueba en SQLite porque el mecanismo es agnóstico del dialecto; el espejo con los
//! módulos reales sobre un Postgres real vive en `postgres_install_e2e.rs`.
use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::Runtime;
use serde_json::json;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join(name)
}

async fn applied(rt: &Runtime, module_id: &str) -> Vec<String> {
    let mut p = Params::new();
    p.insert("module_id".into(), json!(module_id));
    rt.db_for_test()
        .query(
            "SELECT filename FROM _hub_migrations WHERE module_id = :module_id ORDER BY filename",
            &p,
        )
        .await
        .unwrap()
        .rows
        .into_iter()
        .map(|r| r["filename"].as_str().unwrap().to_string())
        .collect()
}

/// Manifest SIN lista de migraciones para el dialecto activo, pero con el `.sql` en el
/// paquete (forma exacta de `customers` en Postgres): se aplica desde disco.
#[tokio::test]
async fn empty_manifest_list_applies_package_migrations() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture("fixture_migunion_empty"))
        .await
        .expect("instalar");

    assert_eq!(
        applied(&rt, "migunion_empty").await,
        ["migrations/postgres/001_init.sql"],
        "la migración del paquete se aplica aunque el manifest no la liste"
    );
    // La tabla existe y es usable.
    rt.db_for_test()
        .execute(
            "INSERT INTO migunion_empty_items (id, hub_id, name) VALUES ('i1', 'h1', 'x')",
            &Params::new(),
        )
        .await
        .expect("la tabla del módulo debe existir tras instalar");
}

/// Manifest PARCIAL (lista 002 pero no 001, forma exacta de `invoice`): la unión aplica
/// ambas en orden de nombre — 001 primero — y los ficheros no-.sql se ignoran.
#[tokio::test]
async fn partial_manifest_list_applies_union_in_name_order() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture("fixture_migunion_partial"))
        .await
        .expect("instalar (002 sola fallaría: ALTER sobre tabla inexistente)");

    assert_eq!(
        applied(&rt, "migunion_partial").await,
        [
            "migrations/postgres/001_init.sql",
            "migrations/postgres/002_add_note.sql"
        ],
        "unión manifest∪disco en orden de nombre; README.txt ignorado"
    );
    rt.db_for_test()
        .execute(
            "INSERT INTO migunion_partial_items (id, hub_id, name, note) VALUES ('i1', 'h1', 'x', 'n')",
            &Params::new(),
        )
        .await
        .expect("001 (tabla) y 002 (columna note) aplicadas");
}

/// Reinstalar no reaplica: el dedupe por `_hub_migrations` cubre también las de la unión.
#[tokio::test]
async fn reinstall_does_not_reapply_union_migrations() {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture("fixture_migunion_partial"))
        .await
        .unwrap();
    rt.install_from_dir(&fixture("fixture_migunion_partial"))
        .await
        .expect("reinstalar");

    assert_eq!(
        applied(&rt, "migunion_partial").await.len(),
        2,
        "reinstalar no duplica registros ni reaplica migraciones"
    );
}
