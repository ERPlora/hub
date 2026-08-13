//! GATE pm#16 — instalación + list-queries + blueprint seed de los packs sectoriales
//! (restaurante / beauty) sobre **Postgres** real (Hub Cloud / demo del SaaS).
//!
//! Reproduce el "no se despliega en prod": la demo del SaaS corre sobre Postgres; si un
//! módulo trae un patrón que SQLite tolera y Postgres rechaza (boolean→INTEGER, EXISTS→INTEGER,
//! columnas sin cualificar en ON CONFLICT, multi-statement en un sql[]), su install/migración
//! o su query revientan en la demo aunque en SQLite (CI de módulos) todo esté verde.
//!
//! No paniquea al primer fallo: acumula TODOS los reds (módulo + fase + error) y falla al final
//! con el informe completo, para arreglar/mergear el lote de una pasada.
//!
//! Requiere un Postgres real (ignorado por defecto):
//! ```sh
//! DATABASE_URL=postgres://erplora:PASS@localhost:5433/erplora_hubtest \
//!   cargo test -p erplora-runtime --test sector_packs_pg_e2e -- --ignored --test-threads=1 --nocapture
//! ```
use std::path::PathBuf;

use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::{RequestContext, Runtime};

fn module_dir(id: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(id)
}

/// Resuelto por el MISMO sitio que los módulos (`e2e_support`, hub#541): una ruta relativa
/// hardcodeada aquí no resuelve desde un worktree fuera del monorepo y el test moría con un
/// `NotFound` pelado en vez de poder apuntarse con `ERPLORA_BLUEPRINTS_DIR`.
fn blueprint_seed(sector: &str) -> PathBuf {
    erplora_runtime::e2e_support::blueprints_root()
        .join("starter_catalogs/es")
        .join(sector)
        .join("seed.sql")
}

/// Unión de módulos POS relevantes a los 3 sectores (barbería/peluquería = beauty, restaurante),
/// en orden topológico de `depends_on` (una dependencia siempre antes que su dependiente).
const POS_MODULES_ORDERED: &[&str] = &[
    "taxes",
    "pricing",
    "tables",
    "cash_register",
    "printing",
    "staff",
    "customers",
    "schedules",
    "inventory",   // dep: taxes
    "services",    // dep: taxes
    "sales",       // dep: inventory, taxes
    "invoice",     // dep: taxes, sales  ← DESPUÉS de sales (invoice v1.2.x, hub#540)
    "kitchen",     // dep: sales, inventory
    "appointments",// dep: customers, services
    "reservations",// dep: tables, customers
    "verifactu",   // dep: invoice
    "online_booking", // dep: customers
];

/// Instala el pack en orden de deps; devuelve la lista de fallos (INSTALL <id>: <err>).
async fn install_pack(rt: &mut Runtime, failures: &mut Vec<String>) {
    for id in POS_MODULES_ORDERED {
        if let Err(e) = rt.install_from_dir(&module_dir(id)).await {
            failures.push(format!("INSTALL {id}: {e}"));
        }
    }
}

/// Ejercita cada query `*.list` declarada por los módulos instalados con params vacíos
/// (el motor de listado funciona sin filtros — es la ruta que carga la UI al abrir cada módulo).
/// Un red aquí = tabla no creada (migración no aplicada) o SQL que Postgres rechaza.
async fn exercise_list_queries(rt: &Runtime, ctx: &RequestContext, failures: &mut Vec<String>) {
    for id in POS_MODULES_ORDERED {
        let mj = module_dir(id).join("module.json");
        let Ok(txt) = std::fs::read_to_string(&mj) else { continue };
        let Ok(json) = serde_json::from_str::<serde_json::Value>(&txt) else { continue };
        let Some(queries) = json.get("queries").and_then(|q| q.as_object()) else { continue };
        for name in queries.keys().filter(|n| n.ends_with(".list")) {
            if let Err(e) = rt.execute_query(name, &Params::new(), ctx).await {
                failures.push(format!("QUERY {name}: {e}"));
            }
        }
    }
}

/// Aplica el seed del sector (INSERTs directos en las tablas de módulo) sobre Postgres.
/// Un red aquí = el seed no casa con el esquema Postgres (columna/tipo/sintaxis).
///
/// **Por `Runtime::apply_seed`, no por `execute_batch` (hub#840).** Antes ejecutaba el fichero a
/// pelo, y `execute_batch` no es una puerta que exista en producción: nadie aplica un seed así. El
/// host lo pasa por `HUB_SEED_SQL` y el runtime lo aplica con `seed::apply`, que liga `:hub_id` y
/// acota al hub las filas de identidad que el fichero no acotó. Con la puerta falsa, el test se
/// ponía rojo por un `NOT NULL` que la puerta REAL no produce — y, peor, no probaba nada de lo que
/// el arranque hace de verdad.
async fn apply_blueprint(rt: &Runtime, sector: &str, failures: &mut Vec<String>) {
    let path = blueprint_seed(sector);
    let Ok(sql) = std::fs::read_to_string(&path) else {
        failures.push(format!("SEED {sector}: no se pudo leer {}", path.display()));
        return;
    };
    if let Err(e) = rt.apply_seed(&sql).await {
        failures.push(format!("SEED {sector}: {e}"));
    }
}

async fn run_sector(sector: &str) {
    // Fixtures externas: los módulos viven en `modules-workspace/` (repos hermanos, no en el repo
    // del hub). Si no están presentes (CI del hub aislado), se omite; en local corre.
    if !module_dir("taxes").exists() {
        eprintln!("skip: modules-workspace ausente (fixtures e2e externos del pack '{sector}')");
        return;
    }
    // Esquema efímero por test (ADR-0154): parte de un "hub nuevo" aislado, sin reset manual.
    let db = fresh_db().await;

    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    // El server llama esto al arrancar: crea las tablas de sistema (incl. identidad `hub_user`)
    // que el blueprint necesita para sembrar los cajeros. Sin esto el seed fallaría por hub_user.
    rt.ensure_system_tables().await.expect("ensure_system_tables");
    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);
    let mut failures: Vec<String> = Vec::new();

    install_pack(&mut rt, &mut failures).await;
    exercise_list_queries(&rt, &ctx, &mut failures).await;
    apply_blueprint(&rt, sector, &mut failures).await;

    assert!(
        failures.is_empty(),
        "\n=== {} reds en el pack '{sector}' sobre Postgres ===\n{}\n",
        failures.len(),
        failures.join("\n")
    );
}

#[tokio::test]
async fn restaurant_pack_installs_and_seeds_on_postgres() {
    run_sector("restaurant").await;
}

#[tokio::test]
async fn beauty_pack_installs_and_seeds_on_postgres() {
    run_sector("beauty").await;
}
