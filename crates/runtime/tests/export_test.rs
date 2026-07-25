//! E2E ROJOS (TDD, plan ADR-0113 Fase 1) del EXPORT del hub a blueprint.
//!
//! Contrato: `export_hub` vuelca el estado del hub a un bundle `manifest.json` + `data/*.sql`
//! SECCIONAL (checkboxes: usuarios · settings · fiscal · media · por-módulo con/sin datos).
//! Garantías que fijan estos tests:
//!   - solo filas del `hub_id` pedido (aislamiento de tenant),
//!   - sin filas `is_deleted=1`,
//!   - SQL con el placeholder `__HUB_ID__` (nunca el hub_id literal — ADR-0072),
//!   - módulo seleccionado sin «datos» → en `manifest.modules` pero SIN `data/<id>.sql`,
//!   - `manifest.sha256` cubre exactamente los ficheros del bundle,
//!   - el manifest es la fuente de verdad (locale, secciones) — a prueba de renombres del zip.
//!
//! Patrón de los e2e existentes (inventory_e2e.rs): módulos REALES de modules-workspace
//! contra SQLite en memoria, cero mocks. La implementación de `export_hub` es columna del
//! humano; estos tests van primero y deben FALLAR (unimplemented!) hasta la Fase 1.

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::export::{export_hub, ExportSelection, ModuleDataSelection, HUB_ID_PLACEHOLDER, SCHEMA_VERSION};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn modules_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules")
}

fn ctx(hub: &str) -> RequestContext {
    RequestContext::new(hub, "u1", ["*".to_string()])
}

/// Runtime con taxes + inventory reales instalados (inventory depende de taxes).
async fn fresh() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1"); // ctx y runtime comparten hub (como en prod)
    rt.install_from_dir(&modules_root().join("taxes")).await.expect("instalar taxes");
    rt.install_from_dir(&modules_root().join("inventory")).await.expect("instalar inventory");
    rt
}

async fn create_product(rt: &Runtime, hub: &str, name: &str, sku: &str) {
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": name, "sku": sku, "price": 450, "cost": 200, "stock": 10 })),
        &ctx(hub),
    )
    .await
    .unwrap_or_else(|e| panic!("crear producto {name}: {e}"));
}

/// Selección «todo con datos» para taxes+inventory.
fn full_selection() -> ExportSelection {
    ExportSelection {
        users: true,
        settings: true,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![
            ModuleDataSelection { module_id: "taxes".into(), with_data: true },
            ModuleDataSelection { module_id: "inventory".into(), with_data: true },
        ],
    }
}

const CREATED_AT: &str = "2026-07-11T18:00:00Z";

#[tokio::test]
async fn full_export_produces_manifest_and_data_files() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;
    create_product(&rt, "h1", "Té verde", "TEV").await;
    // Dato real de taxes vía su comando (el bloque `seed` del manifest NO lo aplica el runtime
    // local — es del lado Cloud, ADR-0101 —, así que se crea una categoría de verdad).
    rt.execute_command(
        "taxes.categories.create",
        &params(json!({ "key": "barberia.corte", "name": "Corte de pelo" })),
        &ctx("h1"),
    )
    .await
    .expect("crear categoría fiscal");

    let bundle = export_hub(&rt, "h1", &full_selection(), "barberia", "es", CREATED_AT)
        .await
        .expect("export completo");

    // Manifest = fuente de verdad del bundle.
    let m = &bundle.manifest;
    assert_eq!(m.schema_version, SCHEMA_VERSION);
    assert_eq!(m.name, "barberia");
    assert_eq!(m.locale, "es");
    assert_eq!(m.created_at, CREATED_AT);

    // Los dos módulos, con datos, y con la versión REAL de su module.json.
    let taxes = m.modules.iter().find(|x| x.id == "taxes").expect("taxes en manifest");
    let inventory = m.modules.iter().find(|x| x.id == "inventory").expect("inventory en manifest");
    assert!(taxes.with_data && inventory.with_data);
    assert!(!taxes.version.is_empty() && !inventory.version.is_empty());

    // Secciones y ficheros coherentes.
    for section in ["hub_users", "hub_settings", "modules/taxes", "modules/inventory"] {
        assert!(m.sections.iter().any(|s| s == section), "falta sección {section}");
    }
    assert!(bundle.files.contains_key("data/hub_users.sql"), "falta data/hub_users.sql");
    assert!(bundle.files.contains_key("data/hub_settings.sql"), "falta data/hub_settings.sql");
    assert!(bundle.files.contains_key("data/taxes.sql"), "falta data/taxes.sql");
    assert!(bundle.files.contains_key("data/inventory.sql"), "falta data/inventory.sql");

    // Los datos reales del hub están en el SQL (los productos creados arriba).
    let inv_sql = String::from_utf8(bundle.files["data/inventory.sql"].clone()).unwrap();
    assert!(inv_sql.contains("Café") && inv_sql.contains("Té verde"), "productos ausentes del SQL");
    // Los datos de taxes (categoría creada arriba) también viajan.
    let tax_sql = String::from_utf8(bundle.files["data/taxes.sql"].clone()).unwrap();
    assert!(tax_sql.contains("barberia.corte"), "categoría fiscal ausente del SQL de taxes");
}

#[tokio::test]
async fn export_omits_module_owned_seed_rows_that_collide_on_restore() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    // La demo del SaaS fallaba en `taxes` al restaurar un blueprint (duplicate key
    // ix_tax_cat_hub_key): el módulo AUTO-SIEMBRA al instalarse sus categorías canónicas
    // (is_system=1) y sus alias de fábrica (source='shipped'); si el bundle ADEMÁS los trae como
    // datos, chocan con la auto-siembra en las claves únicas (hub_id,key)/(hub_id,alias). El export
    // NO debe capturar filas propiedad del módulo — las re-siembra el módulo (ADR-0085/0113, opción A).
    let rt = fresh().await; // instala taxes → siembra categorías is_system=1 + alias 'shipped'
    // Categoría de USUARIO (is_system=0) → SÍ debe viajar (no over-exclusión).
    rt.execute_command(
        "taxes.categories.create",
        &params(json!({ "key": "user.custom", "name": "Categoría del usuario" })),
        &ctx("h1"),
    )
    .await
    .expect("crear categoría de usuario");

    let bundle = export_hub(&rt, "h1", &full_selection(), "t", "es", CREATED_AT).await.expect("export");
    let tax_sql = String::from_utf8(bundle.files["data/taxes.sql"].clone()).unwrap();

    // La de USUARIO viaja; las canónicas is_system NO → solo 1 INSERT en taxes_category (tabla con
    // unique (hub_id,key) que crasheaba). "taxes_category (" (espacio+paréntesis) NO casa con
    // "taxes_category_alias (".
    assert!(tax_sql.contains("user.custom"), "la categoría de usuario (is_system=0) debe viajar:\n{tax_sql}");
    let cat_inserts = tax_sql.matches("INSERT INTO taxes_category (").count();
    assert_eq!(cat_inserts, 1, "solo la categoría de usuario debe viajar (las is_system no):\n{tax_sql}");
    // Ningún alias de fábrica ('shipped') viaja (tabla con unique (hub_id,alias) que crasheaba).
    assert!(
        !tax_sql.contains("INSERT INTO taxes_category_alias"),
        "los alias 'shipped' NO deben viajar (los re-siembra el módulo):\n{tax_sql}"
    );
}

#[tokio::test]
async fn exported_sql_uses_hub_id_placeholder_never_the_literal() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;

    let bundle = export_hub(&rt, "h1", &full_selection(), "barberia", "es", CREATED_AT)
        .await
        .expect("export");

    for (path, bytes) in &bundle.files {
        let sql = String::from_utf8(bytes.clone()).unwrap();
        // El hub_id de origen NUNCA viaja: el import inyecta el del destino (ADR-0072).
        assert!(!sql.contains("'h1'"), "{path} contiene el hub_id literal");
        if path.starts_with("data/") && !sql.trim().is_empty() {
            assert!(sql.contains(HUB_ID_PLACEHOLDER), "{path} sin placeholder {HUB_ID_PLACEHOLDER}");
        }
    }
}

#[tokio::test]
async fn tenant_isolation_other_hub_rows_excluded() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;
    create_product(&rt, "h2", "Secreto Ajeno", "SEC").await;

    let bundle = export_hub(&rt, "h1", &full_selection(), "barberia", "es", CREATED_AT)
        .await
        .expect("export h1");

    let inv_sql = String::from_utf8(bundle.files["data/inventory.sql"].clone()).unwrap();
    assert!(inv_sql.contains("Café"));
    assert!(!inv_sql.contains("Secreto Ajeno"), "fuga de datos de otro tenant en el export");
}

#[tokio::test]
async fn soft_deleted_rows_are_not_exported() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Vivo", "VIV").await;
    create_product(&rt, "h1", "Borrado", "BOR").await;

    // Soft-delete por el comando real del módulo (contrato de fila: is_deleted/deleted_at).
    // `execute_query` devuelve las filas directamente (Vec<Json>), sin envoltorio `rows`.
    let rows = rt
        .execute_query("inventory.products.list", &params(json!({})), &ctx("h1"))
        .await
        .expect("listar productos");
    let id = rows
        .iter()
        .find(|p| p["name"] == "Borrado")
        .and_then(|p| p["id"].as_str().map(str::to_string))
        .expect("precondición: el producto existe antes del delete");
    // El schema del delete (schemas/product_id.json) pide `product_id`, no `id`.
    rt.execute_command("inventory.products.delete", &params(json!({ "product_id": id })), &ctx("h1"))
        .await
        .expect("soft-delete");

    let bundle = export_hub(&rt, "h1", &full_selection(), "barberia", "es", CREATED_AT)
        .await
        .expect("export");
    let inv_sql = String::from_utf8(bundle.files["data/inventory.sql"].clone()).unwrap();
    assert!(inv_sql.contains("Vivo"));
    assert!(!inv_sql.contains("Borrado"), "una fila soft-deleted viajó en el export");
}

#[tokio::test]
async fn module_without_data_is_listed_but_not_dumped() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;

    let mut sel = full_selection();
    sel.modules = vec![
        ModuleDataSelection { module_id: "taxes".into(), with_data: true },
        // inventory: checkbox «módulo» marcado, checkbox «datos» SIN marcar.
        ModuleDataSelection { module_id: "inventory".into(), with_data: false },
    ];

    let bundle = export_hub(&rt, "h1", &sel, "barberia", "es", CREATED_AT).await.expect("export");

    let inv = bundle.manifest.modules.iter().find(|x| x.id == "inventory").expect("inventory listado");
    assert!(!inv.with_data);
    assert!(!bundle.files.contains_key("data/inventory.sql"), "no debía volcar datos de inventory");
    assert!(
        !bundle.manifest.sections.iter().any(|s| s == "modules/inventory"),
        "sección modules/inventory de más"
    );
    // El módulo CON datos sí viaja completo.
    assert!(bundle.files.contains_key("data/taxes.sql"));
}

#[tokio::test]
async fn deselected_sections_are_absent() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;

    let sel = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection { module_id: "taxes".into(), with_data: true }],
    };
    let bundle = export_hub(&rt, "h1", &sel, "solo-taxes", "es", CREATED_AT).await.expect("export");

    assert!(!bundle.files.contains_key("data/hub_users.sql"));
    assert!(!bundle.files.contains_key("data/hub_settings.sql"));
    for s in ["hub_users", "hub_settings", "fiscal", "media"] {
        assert!(!bundle.manifest.sections.iter().any(|x| x == s), "sección {s} no seleccionada presente");
    }
}

/// Las tablas de VÍNCULO (M2M) son joins puros SIN `hub_id` propio (`inventory_product_categories`,
/// `customers_customer_{groups,tags}`). El export las saltaba en silencio —«sin hub_id no es
/// por-tenant»— así que un blueprint (y, con el mismo motor, un BACKUP) perdía la categoría de cada
/// producto: 280 productos aterrizaban sin categoría, el TPV sin pestañas y el KDS sin enrutar.
/// Contrato: se vuelcan, y se acotan al hub por la **FK declarada** hacia su tabla padre (que sí
/// lleva `hub_id`) — no por adivinar nombres de columna.
#[tokio::test]
async fn join_tables_without_hub_id_are_exported_scoped_by_their_parent() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;

    // Dos hubs con su propia categoría + producto ligados entre sí.
    for (hub, sku, cat) in [("h1", "CAF", "Cafés"), ("h2", "TEA", "Tés")] {
        create_product(&rt, hub, "Producto", sku).await;
        rt.execute_command(
            "inventory.categories.create",
            &params(json!({ "name": cat, "slug": cat, "icon": "cube-outline",
                            "color": "#3880ff", "description": "", "order": 0 })),
            &ctx(hub),
        )
        .await
        .unwrap();
        let prods = rt.execute_query("inventory.products.list", &Params::new(), &ctx(hub)).await.unwrap();
        let cats = rt.execute_query("inventory.categories.list", &Params::new(), &ctx(hub)).await.unwrap();
        rt.execute_command(
            "inventory.products.add_category",
            &params(json!({
                "product_id": prods[0]["id"].as_str().unwrap(),
                "category_id": cats[0]["id"].as_str().unwrap(),
            })),
            &ctx(hub),
        )
        .await
        .unwrap();
    }

    let bundle = export_hub(&rt, "h1", &full_selection(), "restaurante", "es", CREATED_AT)
        .await
        .expect("export");
    let sql = String::from_utf8(bundle.files["data/inventory.sql"].clone()).unwrap();

    assert!(
        sql.contains("INSERT INTO inventory_product_categories"),
        "el vínculo producto↔categoría no viaja en el bundle:\n{sql}"
    );
    // Aislamiento de tenant: solo el vínculo de h1 (el de h2 tiene otros ids).
    let vinculos = sql.matches("INSERT INTO inventory_product_categories").count();
    assert_eq!(vinculos, 1, "esperado 1 vínculo (el de h1), hay {vinculos}:\n{sql}");
    // Idempotencia: re-aplicar el bundle no puede duplicar (PK compuesta, sin columna `id`).
    for line in sql.lines().filter(|l| l.contains("inventory_product_categories")) {
        assert!(line.contains("WHERE NOT EXISTS"), "vínculo sin guarda de idempotencia: {line}");
    }
}

#[tokio::test]
async fn sha256_covers_exactly_the_bundle_files() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;

    let bundle = export_hub(&rt, "h1", &full_selection(), "barberia", "es", CREATED_AT)
        .await
        .expect("export");

    // Cobertura exacta: cada fichero tiene hash y no hay hashes huérfanos.
    for path in bundle.files.keys() {
        let h = bundle.manifest.sha256.get(path).unwrap_or_else(|| panic!("{path} sin sha256"));
        assert_eq!(h.len(), 64, "{path}: sha256 no es hex de 64");
        assert!(h.chars().all(|c| c.is_ascii_hexdigit()), "{path}: sha256 no-hex");
    }
    for path in bundle.manifest.sha256.keys() {
        assert!(bundle.files.contains_key(path), "sha256 huérfano para {path}");
    }
}
