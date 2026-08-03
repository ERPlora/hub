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
use erplora_runtime::export::{export_hub, BundlePurpose, ExportSelection, ModuleDataSelection, HUB_ID_PLACEHOLDER, SCHEMA_VERSION};
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
        purpose: Default::default(),
    }
}

const CREATED_AT: &str = "2026-07-11T18:00:00Z";

/// 🔴 [ADR-0195] Una **plantilla pública** no puede llevar identidades ni datos fiscales.
///
/// Lo que había: el `restaurante` v1.0.2 del catálogo —descargable por cualquiera— traía cuatro
/// filas de `hub_user` con su ROL y su `pin_hash` en el formato legacy `sha256("{sal}:{pin}")`,
/// con la **sal dentro del propio artefacto**. Un PIN son 4 dígitos: las cuatro se revierten en
/// 0,00 s, y `Demo` tenía rol **admin** con PIN `0000`. Quien descargara la plantilla tenía PIN de
/// administrador en TODO hub que la hubiese importado.
///
/// La casilla «Usuarios» venía marcada por defecto, pero desmarcarla no es la solución: una
/// casilla no es un control. Con `purpose: Template` las secciones **no entran en el bundle**.
#[tokio::test]
async fn una_plantilla_no_exporta_identidades_ni_fiscal() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;

    // Se PIDEN usuarios y fiscal explícitamente: el propósito debe ganar a la casilla.
    let seleccion = ExportSelection {
        users: true,
        fiscal: true,
        purpose: BundlePurpose::Template,
        ..full_selection()
    };
    let bundle = export_hub(&rt, "h1", &seleccion, "restaurante", "es", CREATED_AT)
        .await
        .expect("export de plantilla");

    assert!(
        !bundle.files.contains_key("data/hub_users.sql"),
        "una plantilla pública NO puede llevar identidades: {:?}",
        bundle.files.keys().collect::<Vec<_>>()
    );
    assert!(
        !bundle.manifest.sections.iter().any(|s| s == "hub_users" || s == "fiscal"),
        "el manifest no puede anunciar secciones de identidad/fiscal: {:?}",
        bundle.manifest.sections
    );
    assert_eq!(bundle.manifest.purpose, BundlePurpose::Template);

    // …y lo que SÍ es una plantilla sigue viajando entero: los datos de negocio.
    let inv = String::from_utf8(bundle.files["data/inventory.sql"].clone()).unwrap();
    assert!(inv.contains("Café"), "una plantilla debe llevar los datos de negocio");
}

/// El espejo: un **backup/migración** sigue llevándolo TODO. Sin identidades, restaurar perdería
/// roles y PINs, y `get_or_link_cloud_user` recrearía a un `employee` como admin (ADR-0113 §1).
/// Es el default cuando el manifest no declara propósito.
#[tokio::test]
async fn un_backup_si_exporta_identidades() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = fresh().await;

    let bundle = export_hub(&rt, "h1", &full_selection(), "backup", "es", CREATED_AT)
        .await
        .expect("export de backup");

    assert_eq!(bundle.manifest.purpose, BundlePurpose::Backup, "el default es backup");
    assert!(bundle.files.contains_key("data/hub_users.sql"), "un backup SÍ lleva identidades");
}

#[tokio::test]
async fn full_export_produces_manifest_and_data_files() {
    if !erplora_runtime::require_modules_workspace() { return; }
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
    if !erplora_runtime::require_modules_workspace() { return; }
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
    if !erplora_runtime::require_modules_workspace() { return; }
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
    if !erplora_runtime::require_modules_workspace() { return; }
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
    if !erplora_runtime::require_modules_workspace() { return; }
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
    if !erplora_runtime::require_modules_workspace() { return; }
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
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = fresh().await;

    let sel = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection { module_id: "taxes".into(), with_data: true }],
        purpose: Default::default(),
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
    if !erplora_runtime::require_modules_workspace() { return; }
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
    if !erplora_runtime::require_modules_workspace() { return; }
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

// ── Orden de sentencias: el PADRE antes que quien lo referencia ──────────────────────────────

/// El volcado tiene que respetar las FK: `inventory_category` ANTES de la tabla de vínculo
/// `inventory_product_categories` que la referencia.
///
/// `list_tables` devuelve el orden de `information_schema`, que NO es orden de dependencias.
/// En un hub real salió la categoría DESPUÉS del vínculo y el import murió con
/// `violates foreign key constraint inventory_product_categories_category_id_fkey` en la
/// sentencia 281 de 579 — perdiendo la sección ENTERA (el módulo se aplica en bloque): 280
/// productos + 19 categorías a la basura. Los blueprints publicados en julio se salvaron por
/// CASUALIDAD, porque aquel hub devolvió las tablas en un orden que sí colaba.
#[tokio::test]
async fn export_vuelca_las_tablas_en_orden_de_dependencia() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = fresh().await;
    rt.execute_command(
        "inventory.categories.create",
        &params(json!({ "name": "Bebidas" })),
        &ctx("h1"),
    )
    .await
    .expect("crear categoría");
    let cats = rt
        .execute_query("inventory.categories.list", &params(json!({})), &ctx("h1"))
        .await
        .expect("listar categorías");
    let cat_id = cats[0]["id"].as_str().expect("id de categoría").to_string();
    create_product(&rt, "h1", "Café", "CAF-1").await;
    let prods = rt
        .execute_query("inventory.products.list", &params(json!({})), &ctx("h1"))
        .await
        .expect("listar productos");
    let prod_id = prods[0]["id"].as_str().expect("id de producto").to_string();
    rt.execute_command(
        "inventory.products.add_category",
        &params(json!({ "product_id": prod_id, "category_id": cat_id })),
        &ctx("h1"),
    )
    .await
    .expect("asignar categoría al producto");

    let bundle = export_hub(&rt, "h1", &full_selection(), "test", "es", "2026-07-31T00:00:00Z")
        .await
        .expect("export");
    let sql = String::from_utf8(bundle.files["data/inventory.sql"].clone()).unwrap();

    let pos_categoria = sql.find("INSERT INTO inventory_category ").expect("volcó categorías");
    let pos_vinculo = sql
        .find("INSERT INTO inventory_product_categories ")
        .expect("volcó los vínculos producto↔categoría");
    assert!(
        pos_categoria < pos_vinculo,
        "la categoría debe ir ANTES del vínculo que la referencia, o el import se cae por FK \
         y pierde la sección entera:\n{sql}"
    );
}

// ── El export no reparte la cuenta Cloud de quien exporta ────────────────────────────────────

/// `hub_user` se vuelca entero (no lleva `hub_id`: es identidad por despliegue), así que el
/// usuario que dispara el export viaja DENTRO del bundle. Publicando eso como blueprint, cada
/// hub de cliente que lo importe se lleva esa cuenta Cloud como usuario suyo — con su rol — y
/// el login cloud casa por `cloud_user_id` y entra.
///
/// Se corta el VÍNCULO, no la fila: `export_hub` es también el motor del backup y de la
/// migración de un hub entre despliegues (ADR-0113 §1), y tirar la fila perdería el rol de
/// cada usuario Cloud — al restaurar los recrea `get_or_link_cloud_user` con
/// `HUB_DEFAULT_ROLE` (por defecto `admin`), así que un `employee` volvería como ADMIN.
/// Con `cloud_user_id = NULL` viajan nombre, rol y PIN, y no viaja la cuenta del SaaS.
#[tokio::test]
async fn export_desvincula_los_usuarios_de_su_cuenta_cloud_sin_perder_su_rol() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let rt = fresh().await;
    erplora_runtime::identity::create_user(rt.db(), "Manager", "1234", "manager", None)
        .await
        .expect("usuario local");
    erplora_runtime::identity::create_user(rt.db(), "support", "", "owner", Some("4"))
        .await
        .expect("usuario cloud");

    let bundle = export_hub(&rt, "h1", &full_selection(), "test", "es", "2026-07-31T00:00:00Z")
        .await
        .expect("export");
    let sql = String::from_utf8(bundle.files["data/hub_users.sql"].clone()).unwrap();

    assert!(sql.contains("Manager"), "el usuario local es plantilla y debe viajar:\n{sql}");
    assert!(
        sql.contains("support") && sql.contains("owner"),
        "el usuario Cloud debe viajar CON su rol (es backup, no solo blueprint):\n{sql}"
    );
    assert!(
        !sql.contains("'4'"),
        "…pero SIN el vínculo a la cuenta Cloud (cloud_user_id): eso es lo que repartiría \
         nuestra cuenta a cada hub que importe el blueprint:\n{sql}"
    );
}

// ── La config fiscal del NEGOCIO no viaja salvo que se marque «fiscal» ───────────────────────

/// `verifactu_config` es la identidad fiscal del negocio (NIF y nombre del emisor, entorno,
/// `auto_transmit`, ruta/clave del certificado), no plantilla ni dato de catálogo.
///
/// Iba en el volcado del módulo `verifactu` como una tabla más, así que el blueprint publicado
/// de julio sembraba `issuer_nif='B12345678'` + `auto_transmit=1` + `environment='testing'` en
/// el hub de CADA cliente que lo importara: un negocio real arrancaba con el NIF de otro
/// configurado y la transmisión automática encendida. Solo debe viajar si el usuario marca
/// explícitamente la sección `fiscal` (que es la que ya mueve el certificado, ADR-0113 §2).
#[tokio::test]
async fn la_config_fiscal_del_negocio_solo_viaja_si_se_marca_fiscal() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    for m in ["taxes", "inventory", "sales", "invoice", "verifactu"] {
        rt.install_from_dir(&modules_root().join(m))
            .await
            .unwrap_or_else(|e| panic!("instalar {m}: {e}"));
    }
    let mut p = Params::new();
    p.insert("hub".into(), json!("h1"));
    rt.db()
        .execute(
            "INSERT INTO verifactu_config (id, hub_id, issuer_nif, issuer_name, environment, \
             enabled, auto_transmit, is_deleted, created_at, updated_at) \
             VALUES ('cfg1', :hub, 'B12345678', 'Restaurante Ejemplo SL', 'testing', 1, 1, 0, \
             '2026-07-31T00:00:00Z', '2026-07-31T00:00:00Z')",
            &p,
        )
        .await
        .expect("sembrar config fiscal");

    let seleccion = |fiscal: bool| ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal,
        media: false,
        modules: vec![ModuleDataSelection { module_id: "verifactu".into(), with_data: true }],
        purpose: Default::default(),
    };

    let sin = export_hub(&rt, "h1", &seleccion(false), "t", "es", "2026-07-31T00:00:00Z")
        .await
        .expect("export sin fiscal");
    let sql_sin = String::from_utf8(sin.files["data/verifactu.sql"].clone()).unwrap();
    assert!(
        !sql_sin.contains("B12345678"),
        "sin marcar «fiscal», el NIF del emisor NO puede viajar:\n{sql_sin}"
    );

    let con = export_hub(&rt, "h1", &seleccion(true), "t", "es", "2026-07-31T00:00:00Z")
        .await
        .expect("export con fiscal");
    let sql_con = String::from_utf8(con.files["data/verifactu.sql"].clone()).unwrap();
    assert!(
        sql_con.contains("B12345678"),
        "marcando «fiscal» (backup/migración de hub) SÍ debe viajar:\n{sql_con}"
    );
}

// ── Orden DENTRO de una tabla: el padre antes que el hijo (FK a sí misma) ────────────────────

/// Ordenar las TABLAS entre sí no basta: `services_category` y `taxes_rule` tienen una FK a sí
/// mismas (`parent_id`), y `fetch_rows` hace `SELECT *` sin `ORDER BY`, así que las filas salen
/// en el orden físico de la tabla. Si el hijo sale antes que su padre, el INSERT revienta por FK
/// y se pierde la sección entera — el mismo fallo que el orden de tablas, un nivel más abajo.
#[tokio::test]
async fn export_ordena_las_filas_padre_antes_que_hija_en_tablas_autorreferenciadas() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    for m in ["taxes", "services"] {
        rt.install_from_dir(&modules_root().join(m))
            .await
            .unwrap_or_else(|e| panic!("instalar {m}: {e}"));
    }
    rt.execute_command(
        "services.categories.create",
        &params(json!({ "name": "Padre", "slug": "padre", "description": "",
                        "parent_id": null, "icon": "", "color": "", "sort_order": 0 })),
        &ctx("h1"),
    )
    .await
    .expect("crear categoría padre");
    let cats = rt
        .execute_query("services.categories.list", &params(json!({})), &ctx("h1"))
        .await
        .expect("listar categorías");
    let padre_id = cats[0]["id"].as_str().expect("id del padre").to_string();
    rt.execute_command(
        "services.categories.create",
        &params(json!({ "name": "Hija", "slug": "hija", "description": "",
                        "parent_id": padre_id, "icon": "", "color": "", "sort_order": 1 })),
        &ctx("h1"),
    )
    .await
    .expect("crear categoría hija");
    // Reescribe la fila del PADRE tocando una columna INDEXADA (`slug`, índice único): eso
    // fuerza un update no-HOT, la fila nueva se escribe al final del heap y el `SELECT *` la
    // devuelve DESPUÉS de la hija — que es justo el orden que revienta al importar.
    rt.execute_command(
        "services.categories.update",
        &params(json!({ "category_id": padre_id, "name": "Padre (renombrado)", "slug": "padre-renombrado",
                        "description": "", "parent_id": null, "icon": "", "color": "",
                        "sort_order": 0, "is_active": 1 })),
        &ctx("h1"),
    )
    .await
    .expect("renombrar el padre");

    let seleccion = ExportSelection {
        users: false,
        settings: false,
        settings_items: None,
        fiscal: false,
        media: false,
        modules: vec![ModuleDataSelection { module_id: "services".into(), with_data: true }],
        purpose: Default::default(),
    };
    let bundle = export_hub(&rt, "h1", &seleccion, "t", "es", "2026-07-31T00:00:00Z")
        .await
        .expect("export");
    let sql = String::from_utf8(bundle.files["data/services.sql"].clone()).unwrap();

    let pos_padre = sql.find("Padre (renombrado)").expect("volcó el padre");
    let pos_hija = sql.find("Hija").expect("volcó la hija");
    assert!(
        pos_padre < pos_hija,
        "la fila padre debe ir ANTES de la hija que la referencia por parent_id:\n{sql}"
    );
}
