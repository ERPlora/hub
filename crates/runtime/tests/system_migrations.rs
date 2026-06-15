//! Migraciones de sistema (hub#37) + `hub_module` hub-scoped (hub#31 / ADR-0005).
//!
//! Cubre los criterios de aceptación:
//!  - #37: un cambio de esquema de sistema llega a un `erplora.db` **existente**; idempotente al
//!    re-arrancar; SQLite (test real) + Postgres (`#[ignore]` si no hay `DATABASE_URL`).
//!  - #31: dos hubs en la misma BD tienen sets de módulos distintos; instalar/activar/desinstalar
//!    en un hub no afecta a otro; las migraciones de módulo siguen convergiendo una sola vez (eso
//!    es `_hub_migrations`, intacto).
use std::path::PathBuf;

use erplora_db::{DatabaseAdapter, Params, SqliteAdapter};
use erplora_runtime::{installer, system_migrations, ModuleStatus, Runtime};
use serde_json::json;

fn fixture() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests/fixture_inventory")
}

/// Ruta a un fichero SQLite temporal único (necesitamos persistencia entre "reinicios": un
/// in-memory vive por conexión). Borra restos previos.
fn temp_db_path(tag: &str) -> PathBuf {
    let p = std::env::temp_dir().join(format!("erplora-systest-{tag}-{}.db", std::process::id()));
    let _ = std::fs::remove_file(&p);
    p
}

async fn open(path: &PathBuf) -> SqliteAdapter {
    SqliteAdapter::connect(&format!("sqlite://{}?mode=rwc", path.display()))
        .await
        .expect("abrir sqlite de fichero")
}

/// Copia recursiva mínima de un directorio (para montar un dir de módulos de test).
fn copy_dir(src: &PathBuf, dst: &PathBuf) {
    std::fs::create_dir_all(dst).unwrap();
    for entry in std::fs::read_dir(src).unwrap() {
        let entry = entry.unwrap();
        let from = entry.path();
        let to = dst.join(entry.file_name());
        if from.is_dir() {
            copy_dir(&from, &to);
        } else {
            std::fs::copy(&from, &to).unwrap();
        }
    }
}

fn p(pairs: &[(&str, serde_json::Value)]) -> Params {
    let mut m = Params::new();
    for (k, v) in pairs {
        m.insert((*k).into(), v.clone());
    }
    m
}

// ── #37 — el cambio de esquema de sistema llega a un erplora.db EXISTENTE ─────────────────────

#[tokio::test]
async fn system_migration_reaches_existing_db_and_is_idempotent() {
    let path = temp_db_path("upgrade");

    // 1) Simula un `erplora.db` VIEJO: tabla `hub_module` con el esquema v0 (sin hub_id) y una
    // fila ya existente (como un hub que se actualizó pero la BD sobrevivió al update de Tauri).
    {
        let db = open(&path).await;
        db.execute_batch(
            "CREATE TABLE IF NOT EXISTS hub_module (\
               module_id TEXT PRIMARY KEY, version TEXT NOT NULL, status TEXT NOT NULL, \
               installed_at TEXT NOT NULL, updated_at TEXT NOT NULL);",
        )
        .await
        .unwrap();
        db.execute(
            "INSERT INTO hub_module (module_id, version, status, installed_at, updated_at) \
             VALUES (:id, '1.0.0', 'active', :now, :now)",
            &p(&[("id", json!("legacy_mod")), ("now", json!("2026-01-01T00:00:00Z"))]),
        )
        .await
        .unwrap();
    }

    // 2) "Re-arranque" con el hub_id del despliegue: aplica las migraciones de sistema.
    let hub_a = "hub-AAAA";
    {
        let db = open(&path).await;
        system_migrations::apply(&db, hub_a).await.unwrap();

        // La columna hub_id existe y la fila legacy quedó sellada con el hub_id del despliegue.
        let rows = db
            .query("SELECT hub_id, module_id FROM hub_module WHERE module_id = 'legacy_mod'", &Params::new())
            .await
            .unwrap()
            .rows;
        assert_eq!(rows.len(), 1, "la fila legacy debe seguir existiendo tras migrar");
        assert_eq!(rows[0]["hub_id"], json!(hub_a), "hub_id sellado al del despliegue");

        // La migración v1 quedó registrada en la tabla de control.
        let reg = db
            .query("SELECT version FROM _hub_system_migrations WHERE version = 1", &Params::new())
            .await
            .unwrap()
            .rows;
        assert_eq!(reg.len(), 1, "v1 registrada en _hub_system_migrations");
    }

    // 3) Idempotencia: re-aplicar NO vuelve a correr v1 (no duplica filas ni rompe). Una segunda
    // fila legacy NO debe perder su hub_id ni reaparecer la columna duplicada.
    {
        let db = open(&path).await;
        system_migrations::apply(&db, hub_a).await.unwrap();
        let count_after_first = db
            .query("SELECT version FROM _hub_system_migrations", &Params::new())
            .await
            .unwrap()
            .rows
            .len();
        system_migrations::apply(&db, hub_a).await.unwrap();
        let reg = db
            .query("SELECT version FROM _hub_system_migrations", &Params::new())
            .await
            .unwrap()
            .rows;
        // Idempotencia: re-aplicar NO añade filas (el recuento no crece). v1 ya estaba; v2+ tampoco
        // se reaplican. El número exacto depende de cuántas migraciones haya definidas en el catálogo.
        assert_eq!(reg.len(), count_after_first, "re-arrancar no reaplica (recuento estable)");
        assert!(reg.iter().any(|r| r["version"] == json!(1)), "v1 sigue registrada");
        // La PK es ahora compuesta: insertar el mismo module_id con otro hub_id NO colisiona.
        db.execute(
            "INSERT INTO hub_module (hub_id, module_id, version, status, installed_at, updated_at) \
             VALUES ('hub-OTHER', 'legacy_mod', '1.0.0', 'active', :now, :now)",
            &p(&[("now", json!("2026-01-02T00:00:00Z"))]),
        )
        .await
        .expect("PK (hub_id, module_id): mismo módulo en otro hub es fila distinta");
    }

    let _ = std::fs::remove_file(&path);
}

// ── #31 — dos hubs en la misma BD: sets de módulos distintos, aislados ────────────────────────

#[tokio::test]
async fn two_hubs_share_db_with_independent_module_sets() {
    let path = temp_db_path("twohubs");

    // Hub A instala inventory desde disco.
    {
        let db = open(&path).await;
        let mut rt_a = Runtime::with_hub_id(Box::new(db), "hub-A");
        rt_a.install_from_dir(&fixture()).await.unwrap();
    }
    // Hub B sobre la MISMA BD: arranca sin instalar (no hereda el set de A).
    {
        let db = open(&path).await;
        let rt_b = Runtime::with_hub_id(Box::new(db), "hub-B");
        rt_b.ensure_system_tables().await.unwrap();
    }

    // Verificación por SQL directo: hub_module tiene la fila de A pero ninguna de B.
    {
        let db = open(&path).await;
        let rows_a = db
            .query("SELECT module_id FROM hub_module WHERE hub_id = 'hub-A'", &Params::new())
            .await
            .unwrap()
            .rows;
        let rows_b = db
            .query("SELECT module_id FROM hub_module WHERE hub_id = 'hub-B'", &Params::new())
            .await
            .unwrap()
            .rows;
        assert_eq!(rows_a.len(), 1, "hub A tiene inventory");
        assert_eq!(rows_a[0]["module_id"], json!("inventory"));
        assert!(rows_b.is_empty(), "hub B no comparte el set de módulos de A");
    }

    let _ = std::fs::remove_file(&path);
}

#[tokio::test]
async fn uninstall_in_one_hub_does_not_affect_another() {
    let path = temp_db_path("uninstall-isolated");

    // Ambos hubs instalan inventory (cada uno su fila en hub_module).
    {
        let db = open(&path).await;
        let mut rt_a = Runtime::with_hub_id(Box::new(db), "hub-A");
        rt_a.install_from_dir(&fixture()).await.unwrap();
    }
    {
        let db = open(&path).await;
        let mut rt_b = Runtime::with_hub_id(Box::new(db), "hub-B");
        rt_b.install_from_dir(&fixture()).await.unwrap();
    }

    // Hub A desinstala inventory.
    {
        let db = open(&path).await;
        let mut rt_a = Runtime::with_hub_id(Box::new(db), "hub-A");
        rt_a.install_from_dir(&fixture()).await.unwrap(); // re-registra desde disco
        rt_a.uninstall("inventory").await.unwrap();
    }

    // La fila de A desaparece; la de B sigue intacta.
    {
        let db = open(&path).await;
        let rows_a = db
            .query("SELECT module_id FROM hub_module WHERE hub_id = 'hub-A'", &Params::new())
            .await
            .unwrap()
            .rows;
        let rows_b = db
            .query("SELECT module_id FROM hub_module WHERE hub_id = 'hub-B'", &Params::new())
            .await
            .unwrap()
            .rows;
        assert!(rows_a.is_empty(), "A desinstaló inventory");
        assert_eq!(rows_b.len(), 1, "B conserva inventory (aislamiento por hub_id)");
    }

    let _ = std::fs::remove_file(&path);
}

#[tokio::test]
async fn deactivate_in_one_hub_does_not_affect_another() {
    let path = temp_db_path("deactivate-isolated");

    {
        let db = open(&path).await;
        let mut rt_a = Runtime::with_hub_id(Box::new(db), "hub-A");
        rt_a.install_from_dir(&fixture()).await.unwrap();
        rt_a.deactivate("inventory").await.unwrap(); // A desactiva
    }
    {
        let db = open(&path).await;
        let mut rt_b = Runtime::with_hub_id(Box::new(db), "hub-B");
        rt_b.install_from_dir(&fixture()).await.unwrap(); // B lo deja activo
    }

    {
        let db = open(&path).await;
        let st_a = installer::installed_status(&db, "hub-A").await.unwrap();
        let st_b = installer::installed_status(&db, "hub-B").await.unwrap();
        assert_eq!(st_a, vec![("inventory".to_string(), ModuleStatus::Inactive)], "A inactivo");
        assert_eq!(st_b, vec![("inventory".to_string(), ModuleStatus::Active)], "B activo");
    }

    // Y la reconstrucción del Registry de A respeta el estado inactivo persistido por hub: monta
    // un dir con SOLO la copia de inventory y deja que `install_all_from_dir` reconstruya. Aunque
    // `install` deja todo activo, la fase 4 (reconstrucción desde `hub_module` filtrando por hub_id)
    // debe re-aplicar el estado inactivo que A dejó persistido.
    {
        let mods_dir = std::env::temp_dir().join(format!("erplora-mods-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&mods_dir);
        copy_dir(&fixture(), &mods_dir.join("inventory"));

        let db = open(&path).await;
        let mut rt_a = Runtime::with_hub_id(Box::new(db), "hub-A");
        rt_a.install_all_from_dir(&mods_dir).await.unwrap();
        let inv = rt_a.modules().into_iter().find(|m| m.id == "inventory").expect("inventory presente");
        assert_eq!(inv.status, ModuleStatus::Inactive, "A reconstruye inventory como inactivo");

        let _ = std::fs::remove_dir_all(&mods_dir);
    }

    let _ = std::fs::remove_file(&path);
}

// ── #31 — las migraciones de MÓDULO siguen convergiendo una sola vez por BD (_hub_migrations) ──

#[tokio::test]
async fn module_migrations_still_converge_once_per_db() {
    let path = temp_db_path("module-mig-once");

    // Dos hubs instalan inventory sobre la misma BD: las migraciones del módulo (tablas de datos)
    // se aplican UNA sola vez por BD (convergen vía `_hub_migrations(module_id, filename)`), no por
    // hub. Lo comprobamos contando las filas de `_hub_migrations` de inventory tras ambos installs.
    {
        let db = open(&path).await;
        let mut rt_a = Runtime::with_hub_id(Box::new(db), "hub-A");
        rt_a.install_from_dir(&fixture()).await.unwrap();
    }
    let after_a = {
        let db = open(&path).await;
        db.query(
            "SELECT filename FROM _hub_migrations WHERE module_id = 'inventory'",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows
        .len()
    };
    {
        let db = open(&path).await;
        let mut rt_b = Runtime::with_hub_id(Box::new(db), "hub-B");
        rt_b.install_from_dir(&fixture()).await.unwrap();
    }
    let after_b = {
        let db = open(&path).await;
        db.query(
            "SELECT filename FROM _hub_migrations WHERE module_id = 'inventory'",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows
        .len()
    };
    assert!(after_a > 0, "inventory aplicó al menos una migración de módulo");
    assert_eq!(after_a, after_b, "el segundo hub NO reaplica migraciones de módulo (convergen por BD)");

    let _ = std::fs::remove_file(&path);
}

// ── #37/#31 en Postgres (requiere DATABASE_URL; ignorado por defecto como el resto) ───────────

/// Espejo del test de SQLite contra un Postgres real: arranca con una `hub_module` v0 existente,
/// aplica la migración v1 (ALTER aditivo + recompose PK) y verifica que llega a la tabla
/// existente y es idempotente. Limpia las tablas de sistema antes para ser repetible.
///
/// ```sh
/// DATABASE_URL=postgres://user:pass@localhost:5432/erplora_test \
///   cargo test -p erplora-runtime --test system_migrations -- --ignored
/// ```
#[tokio::test]
#[ignore = "requires a real Postgres via DATABASE_URL"]
async fn system_migration_postgres_reaches_existing_table() {
    use erplora_db::PgAdapter;
    let url = std::env::var("DATABASE_URL").expect("set DATABASE_URL");
    let db = PgAdapter::connect(&url).await.expect("connect to postgres");

    // Estado de partida limpio + tabla v0 (sin hub_id) con una fila legacy.
    db.execute_batch(
        "DROP TABLE IF EXISTS _hub_system_migrations; DROP TABLE IF EXISTS hub_module;\
         CREATE TABLE hub_module (\
           module_id TEXT PRIMARY KEY, version TEXT NOT NULL, status TEXT NOT NULL, \
           installed_at TEXT NOT NULL, updated_at TEXT NOT NULL);",
    )
    .await
    .unwrap();
    db.execute(
        "INSERT INTO hub_module (module_id, version, status, installed_at, updated_at) \
         VALUES ('legacy_mod', '1.0.0', 'active', :now, :now)",
        &p(&[("now", json!("2026-01-01T00:00:00Z"))]),
    )
    .await
    .unwrap();

    let hub = "hub-PG";
    system_migrations::apply(&db, hub).await.unwrap();

    let rows = db
        .query("SELECT hub_id FROM hub_module WHERE module_id = 'legacy_mod'", &Params::new())
        .await
        .unwrap()
        .rows;
    assert_eq!(rows[0]["hub_id"], json!(hub), "hub_id sellado al del despliegue");

    // Idempotente.
    system_migrations::apply(&db, hub).await.unwrap();
    let reg = db
        .query("SELECT version FROM _hub_system_migrations", &Params::new())
        .await
        .unwrap()
        .rows;
    assert_eq!(reg.len(), 1, "v1 registrada una sola vez");

    // PK compuesta: mismo módulo en otro hub no colisiona.
    db.execute(
        "INSERT INTO hub_module (hub_id, module_id, version, status, installed_at, updated_at) \
         VALUES ('hub-OTHER', 'legacy_mod', '1.0.0', 'active', :now, :now)",
        &p(&[("now", json!("2026-01-02T00:00:00Z"))]),
    )
    .await
    .expect("PK (hub_id, module_id)");

    // Limpieza.
    db.execute_batch("DROP TABLE IF EXISTS _hub_system_migrations; DROP TABLE IF EXISTS hub_module;")
        .await
        .unwrap();
}
