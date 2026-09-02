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
//! Requiere un Postgres real (sin `--ignored`: el guard de `run_sector` ya salta solo si faltan
//! los fixtures de módulos; con `--ignored` estos tests se FILTRAN y corren 0):
//! ```sh
//! DATABASE_URL=postgres://postgres:test@localhost:5433/hub_test \
//!   cargo test -p erplora-runtime --test sector_packs_pg_e2e -- --test-threads=1 --nocapture
//! ```
use std::path::PathBuf;

use erplora_db::testutil::fresh_db;
use erplora_db::Params;
use erplora_runtime::{RequestContext, Runtime};

fn module_dir(id: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(id)
}

/// The sector seed this e2e applies. It is a fixture **of this repo** (hub#1050).
///
/// It used to be read out of the sibling `blueprints` checkout, from the hand-written catalogue
/// model that ADR-0121 retired: the sector seed is no longer written by hand, it comes out of a
/// hub's Export as a `.blueprint.zip`. That left the hub as the only live consumer of a dead model
/// — blueprints#8 could not delete it without turning this suite red — and made the suite depend on
/// a directory of ANOTHER repo, which a checkout is free not to have.
///
/// Resolved from `CARGO_MANIFEST_DIR`, so it lands wherever the crate itself is: no sibling repo,
/// no `ERPLORA_BLUEPRINTS_DIR` override to point at one, no worktree layout to get right.
fn blueprint_seed(sector: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures/sector_pack_es")
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
    "inventory",      // dep: taxes
    "services",       // dep: taxes
    "sales",          // dep: inventory, taxes
    "invoice",        // dep: taxes, sales  ← DESPUÉS de sales (invoice v1.2.x, hub#540)
    "kitchen",        // dep: sales, inventory
    "appointments",   // dep: customers, services
    "reservations",   // dep: tables, customers
    "verifactu",      // dep: invoice
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

/// Listas de DETALLE cuyo SQL referencia un bind fuera de todo `COALESCE(:p, …)`: desde hub#1086
/// (PR #1112) el motor de listas las EXIGE y responde `missing_required_param` si faltan — ligarlas
/// como NULL era el bug original (`cash_register.movements.list` respondiendo una página vacía
/// «sin movimientos» con los movimientos escritos, QA 21/08). La UI jamás abre estas listas sin
/// su contexto (la sesión de caja, el pack, la fecha visible del calendario), así que el smoke
/// tampoco: les pasa el bind que su SQL declara requerido.
///
/// PINNADO A PROPÓSITO: todo lo que NO está aquí se sigue ejerciendo con params vacíos. Si un
/// módulo publica un bind requerido NUEVO en un `*.list` y nadie lo declara en este mapa, el test
/// vuelve a rojo con `missing_required_param` — la lista de qué queries exigen contexto queda
/// ESCRITA y consciente, no silenciada. Y al revés: los opcionales reales del pack (el
/// `include_archived` de `services.services.list`, envuelto en COALESCE) corren sin params y en
/// verde, que es la prueba sobre PG de que el escáner no da falsos requeridos con su idioma.
const REQUIRED_LIST_BINDS: &[(&str, &[(&str, &str)])] = &[
    // Arqueos y movimientos de UNA sesión de caja — el caso real de hub#1086.
    (
        "cash_register.counts.list",
        &[("session_id", "session-smoke")],
    ),
    (
        "cash_register.movements.list",
        &[("session_id", "session-smoke")],
    ),
    // Líneas de servicios de UN pack.
    (
        "services.package_items.list",
        &[("package_id", "package-smoke")],
    ),
    // Bloqueos a partir de la fecha visible del calendario (ISO 8601; la columna es TEXT).
    (
        "appointments.blocked_times.list",
        &[("from_datetime", "2026-01-01T00:00:00")],
    ),
];

/// Ejercita cada query `*.list` declarada por los módulos instalados: las de contexto con el bind
/// que su SQL exige (ver [`REQUIRED_LIST_BINDS`]), el resto con params vacíos (el motor de listado
/// funciona sin filtros — es la ruta que carga la UI al abrir cada módulo).
/// Un red aquí = tabla no creada (migración no aplicada), SQL que Postgres rechaza, o un bind
/// requerido nuevo que nadie declaró en [`REQUIRED_LIST_BINDS`].
async fn exercise_list_queries(rt: &Runtime, ctx: &RequestContext, failures: &mut Vec<String>) {
    for id in POS_MODULES_ORDERED {
        let mj = module_dir(id).join("module.json");
        let Ok(txt) = std::fs::read_to_string(&mj) else {
            continue;
        };
        let Ok(json) = serde_json::from_str::<serde_json::Value>(&txt) else {
            continue;
        };
        let Some(queries) = json.get("queries").and_then(|q| q.as_object()) else {
            continue;
        };
        for name in queries.keys().filter(|n| n.ends_with(".list")) {
            let mut params = Params::new();
            for (query, binds) in REQUIRED_LIST_BINDS {
                if query == name {
                    for (k, v) in *binds {
                        params.insert((*k).to_string(), serde_json::json!(v));
                    }
                }
            }
            if let Err(e) = rt.execute_query(name, &params, ctx).await {
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
    rt.ensure_system_tables()
        .await
        .expect("ensure_system_tables");
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

/// hub#1050 — the sector seeds are fixtures OF THIS REPO, and must stay that way.
///
/// The two `run_sector` tests need a Postgres and the module fixtures; this one needs neither, so
/// it is the assertion that still holds in a bare checkout. Two things are pinned: the seeds are
/// readable from the crate itself, and the suite does not go back to the hand-written catalogue
/// directory of the sibling `blueprints` repo that ADR-0121 retired. Without the second half,
/// "the fixture lives in the hub" would hold only until the next edit re-pointed the path — which
/// is how that dead model outlived its retirement by six weeks, blocking blueprints#8 the whole
/// time.
#[test]
fn sector_seeds_are_fixtures_of_this_repo() {
    for sector in ["restaurant", "beauty"] {
        let path = blueprint_seed(sector);
        let sql = std::fs::read_to_string(&path).unwrap_or_else(|e| {
            panic!(
                "the '{sector}' seed fixture is unreadable at {}: {e}",
                path.display()
            )
        });
        assert!(
            sql.contains("INSERT INTO"),
            "the '{sector}' fixture must carry the seed statements this suite applies (read {} bytes)",
            sql.len()
        );
    }
    // Spelled in two halves on purpose: written whole, the needle would match itself here and the
    // assertion could never fail.
    let retired_catalog_dir = concat!("starter_", "catalogs");
    assert!(
        !include_str!("sector_packs_pg_e2e.rs").contains(retired_catalog_dir),
        "this suite must not read the retired ADR-0121 catalogue model again: it is what kept \
         blueprints#8 blocked (hub#1050)"
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
