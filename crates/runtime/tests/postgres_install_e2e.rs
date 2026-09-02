//! E2E de instalación de un módulo real sobre **Postgres** (Hub Cloud).
//!
//! Contrato: instalar un módulo en un hub Cloud (Postgres) deja sus tablas creadas y sus
//! queries/commands operativos — exactamente igual que en SQLite (Hub Local). Reproduce el
//! bug sistémico "instalado pero muerto": el manifest de `customers` no lista
//! `migrations.postgres` (aunque `migrations/postgres/001_init.sql` existe en el paquete),
//! `migrations::apply` solo aplica la lista del manifest → 0 migraciones → la tabla no
//! existe → `customers.list` revienta con `relation "customers_customer" does not exist`,
//! pero `install_from_dir` devuelve Ok y `hub_module` queda `active`.
//!
//! Requiere un Postgres real (ignorado por defecto, como `system_migrations.rs`):
//!
//! ```sh
//! DATABASE_URL=postgres://user:pass@localhost:5432/erplora_test \
//!   cargo test -p erplora-runtime --test postgres_install_e2e -- --ignored --test-threads=1
//! ```
//!
//! (`--test-threads=1`: los tests comparten la BD y cada uno resetea las tablas de sistema.)
use std::path::PathBuf;

use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn module_dir(id: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(id)
}

#[tokio::test]
async fn install_on_postgres_applies_migrations_and_queries_work() {
    // Fixtures externas: los módulos viven en `modules-workspace/` (repos hermanos, no en el repo
    // del hub). Si no están presentes (p. ej. CI del hub aislado), se omite; en local corre.
    if !module_dir("customers").exists() {
        eprintln!("skip: modules-workspace ausente (fixtures e2e externos)");
        return;
    }
    // Esquema efímero por test (ADR-0154): "hub nuevo" aislado, sin cleanup manual.
    let db = fresh_db().await;

    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&module_dir("customers"))
        .await
        .expect("instalar customers");

    // Síntoma del bug: el módulo queda `active` en `hub_module`…
    // The runtime is built with `with_hub_id("h1")` (hub#594), so module state lives under "h1".
    let mut p = Params::new();
    p.insert("hub_id".into(), json!("h1"));
    let status = rt
        .db_for_test()
        .query(
            "SELECT status FROM hub_module WHERE hub_id = :hub_id AND module_id = 'customers'",
            &p,
        )
        .await
        .unwrap()
        .rows;
    assert_eq!(
        status[0]["status"],
        json!("active"),
        "install deja el módulo activo"
    );

    // …pero el contrato exige que sus migraciones se hayan aplicado de verdad:
    let applied = rt
        .db_for_test()
        .query(
            "SELECT filename FROM _hub_migrations WHERE module_id = 'customers'",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows;
    assert!(
        !applied.is_empty(),
        "customers debe aplicar sus migraciones Postgres al instalarse (0 aplicadas = módulo muerto)"
    );

    // Y sus capacidades declarativas deben funcionar (la tabla existe), tanto con `search`
    // provisto como SIN él (la UI/el asistente pueden llamar la lista sin parámetros).
    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
    let mut sp = Params::new();
    sp.insert("search".into(), json!("zzz"));
    rt.execute_query("customers.list", &sp, &ctx)
        .await
        .expect("customers.list con search debe funcionar (tabla creada)");
    let rows = rt
        .execute_query("customers.list", &Params::new(), &ctx)
        .await
        .expect("customers.list sin params debe funcionar (search NULL = sin filtro)");
    assert!(rows.is_empty(), "hub recién instalado: sin clientes");
}

/// Caso `invoice`: manifest PARCIAL (lista `002_tax_category_key.sql` —un ALTER— pero no
/// `001_init.sql`). Con la lista literal del manifest el install FALLABA en Postgres
/// (ALTER sobre tabla inexistente); la unión manifest∪paquete aplica 001→002 en orden.
#[tokio::test]
async fn install_invoice_on_postgres_applies_partial_manifest_union() {
    if !module_dir("invoice").exists() {
        eprintln!("skip: modules-workspace ausente (fixtures e2e externos)");
        return;
    }
    // Esquema efímero por test (ADR-0154): "hub nuevo" aislado, sin cleanup manual.
    let db = fresh_db().await;

    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    // `invoice` declara `depends_on: [taxes, sales]` y `sales` a su vez `[inventory, taxes]`: el
    // instalador exige la cadena completa antes que el dependiente. Lo que este test mide sigue
    // siendo SOLO lo de `invoice` (sus `_hub_migrations`), que no cambian por instalar sus deps.
    for dep in ["taxes", "inventory", "sales"] {
        rt.install_from_dir(&module_dir(dep))
            .await
            .unwrap_or_else(|e| panic!("instalar {dep}: {e}"));
    }
    rt.install_from_dir(&module_dir("invoice"))
        .await
        .expect("instalar invoice");

    let applied = rt
        .db_for_test()
        .query(
            "SELECT filename FROM _hub_migrations WHERE module_id = 'invoice' ORDER BY filename",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows;
    let names: Vec<&str> = applied
        .iter()
        .map(|r| r["filename"].as_str().unwrap())
        .collect();
    // The expected list is READ from the module on disk, not written here: `invoice` publishes a
    // migration every few days and a literal list turned this test red on every one of them
    // (hub#959's gate broke on `005_substitution_unique.sql`). What the test measures is the
    // union manifest ∪ package/migrations/postgres/*.sql, applied in filename order — so that
    // union is what it computes.
    let dir = module_dir("invoice");
    let manifest = erplora_runtime::manifest::Manifest::load(&dir).expect("manifest de invoice");
    let mut expected: Vec<String> = manifest
        .migrations
        .postgres
        .iter()
        .map(|e| e.file().to_string())
        .collect();
    for entry in std::fs::read_dir(dir.join("migrations/postgres")).expect("migrations/postgres") {
        let name = entry.unwrap().file_name().to_string_lossy().into_owned();
        let rel = format!("migrations/postgres/{name}");
        if name.ends_with(".sql") && !expected.contains(&rel) {
            expected.push(rel);
        }
    }
    expected.sort();
    assert!(
        expected.len() >= 4,
        "the control: invoice ships at least the four migrations this test was born with: {expected:?}"
    );
    assert_eq!(
        names, expected,
        "unión manifest∪paquete: todas las migraciones Postgres del módulo, en orden"
    );

    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
    let rows = rt
        .execute_query("invoice.list", &Params::new(), &ctx)
        .await
        .expect("invoice.list debe funcionar tras instalar");
    assert!(rows.is_empty(), "hub recién instalado: sin facturas");
}
