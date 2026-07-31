//! E2E ROJOS (TDD, ADR-0170 Fase 1) del RESET del hub — volver el hub a cero.
//!
//! El reset es el **espejo del export**: mismo inventario de tablas (`table_owner` por prefijo
//! más largo, FKs del catálogo), recorrido al revés. Garantías que fijan estos tests:
//!   - **aislamiento de tenant**: la BD es COMPARTIDA por organización (`tenancy.md`); resetear
//!     el hub A no puede tocar una sola fila del hub B — es el riesgo nº 1 de esta feature,
//!   - **borrado duro** (no `is_deleted=1`): un soft-delete masivo rompería los índices únicos
//!     `(hub_id, …)` al reimportar,
//!   - **las filas propiedad del MÓDULO sobreviven** (`is_system=1` · `source='shipped'` ·
//!     `created_by='system'`): las siembra el módulo al INSTALARSE y no las vuelve a sembrar;
//!     borrarlas deja el hub sin IVA de forma irrecuperable (mismo criterio que `is_module_seeded`
//!     del export),
//!   - **orden inverso de FK**: los vínculos M2M sin `hub_id` propio se borran antes que sus
//!     padres, o el DELETE revienta contra la FK,
//!   - **`plan_reset` es dry-run**: cuenta filas REALES (la UI pinta cifras, no adjetivos) y no
//!     borra nada,
//!   - **no te puedes auto-expulsar**: el usuario que ejecuta el reset sobrevive siempre.
//!
//! Patrón de los e2e existentes (`export_test.rs`): módulos REALES de modules-workspace contra
//! Postgres —schema efímero por test, `erplora_db::testutil`—, cero mocks.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::reset::{execute_reset, plan_reset, ResetSelection};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn modules_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules")
}

fn have_modules() -> bool {
    modules_root().exists()
}

fn ctx(hub: &str) -> RequestContext {
    RequestContext::new(hub, "u1", ["*".to_string()])
}

/// Runtime con taxes + inventory reales instalados (inventory depende de taxes).
/// Instalar `taxes` SIEMBRA sus categorías canónicas (`is_system=1`) y alias de fábrica
/// (`source='shipped'`) — justo las filas que el reset debe conservar.
async fn fresh() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
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

/// Cuenta TODAS las filas de `table` del hub (incluidas las soft-deleted: el reset borra de
/// verdad, así que la cuenta cruda es la que manda).
async fn count(rt: &Runtime, table: &str, hub: &str) -> i64 {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub));
    let res = rt
        .db()
        .query(&format!("SELECT count(*) AS n FROM {table} WHERE hub_id = :hub_id"), &p)
        .await
        .unwrap_or_else(|e| panic!("contar {table}: {e}"));
    res.rows[0]["n"].as_i64().expect("count(*) numérico")
}

/// Cuenta filas sin acotar por hub (tablas de VÍNCULO M2M, que no llevan `hub_id`).
async fn count_all(rt: &Runtime, table: &str) -> i64 {
    let res = rt
        .db()
        .query(&format!("SELECT count(*) AS n FROM {table}"), &Params::new())
        .await
        .unwrap_or_else(|e| panic!("contar {table}: {e}"));
    res.rows[0]["n"].as_i64().expect("count(*) numérico")
}

/// Selección que borra los datos de los dos módulos instalados.
fn wipe_modules() -> ResetSelection {
    ResetSelection {
        modules: vec!["taxes".into(), "inventory".into()],
        ..Default::default()
    }
}

const ACTOR: &str = "u1";

// ── 1. El caso base: los datos de usuario se van ────────────────────────────────────────

#[tokio::test]
async fn reset_borra_los_datos_de_usuario_del_hub() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;
    create_product(&rt, "h1", "Té verde", "TEV").await;
    assert_eq!(count(&rt, "inventory_product", "h1").await, 2, "precondición: 2 productos");

    let report = execute_reset(&rt, "h1", &wipe_modules(), ACTOR).await.expect("reset");

    assert_eq!(
        count(&rt, "inventory_product", "h1").await,
        0,
        "tras el reset no puede quedar ningún producto del hub"
    );
    // El informe declara lo que hizo, por sección (contrato que pinta la UI).
    let inv = report
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("el informe debe traer la sección modules/inventory");
    assert!(inv.rows_deleted >= 2, "el informe debe contar las filas borradas, trae {}", inv.rows_deleted);
}

/// Borrado DURO, no `is_deleted=1`: un soft-delete masivo dejaría el hub «vacío» en la UI pero
/// rompería los índices únicos `(hub_id, sku)` al reimportar el catálogo.
#[tokio::test]
async fn reset_borra_de_verdad_no_marca_is_deleted() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;

    execute_reset(&rt, "h1", &wipe_modules(), ACTOR).await.expect("reset");

    // Re-crear el MISMO sku debe funcionar: si el reset hubiera hecho soft-delete, la fila
    // seguiría ahí y el índice único (hub_id, sku) rechazaría este alta.
    create_product(&rt, "h1", "Café", "CAF").await;
    assert_eq!(count(&rt, "inventory_product", "h1").await, 1);
}

// ── 2. 🔴 El riesgo nº 1: BD compartida por organización ────────────────────────────────

/// En Cloud varios hubs de la MISMA organización comparten base de datos y se aíslan por el
/// `hub_id` de cada fila. Un DELETE sin ese `WHERE` —o un `TRUNCATE`— se lleva por delante los
/// datos de los hubs hermanos. Este test es el que impide que eso llegue a producción.
#[tokio::test]
async fn reset_no_toca_ni_una_fila_de_otro_hub_de_la_misma_org() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;
    create_product(&rt, "h2", "Secreto Ajeno", "SEC").await;
    create_product(&rt, "h2", "Otro Ajeno", "SEC2").await;
    rt.execute_command(
        "taxes.categories.create",
        &params(json!({ "key": "vecino.corte", "name": "Del vecino" })),
        &ctx("h2"),
    )
    .await
    .expect("categoría del hub vecino");

    let antes_h2_prod = count(&rt, "inventory_product", "h2").await;
    let antes_h2_cat = count(&rt, "taxes_category", "h2").await;
    assert_eq!(antes_h2_prod, 2, "precondición: el vecino tiene 2 productos");

    execute_reset(&rt, "h1", &wipe_modules(), ACTOR).await.expect("reset de h1");

    assert_eq!(count(&rt, "inventory_product", "h1").await, 0, "h1 sí se resetea");
    assert_eq!(
        count(&rt, "inventory_product", "h2").await,
        antes_h2_prod,
        "🔴 FUGA ENTRE TENANTS: el reset de h1 se llevó productos del hub h2"
    );
    assert_eq!(
        count(&rt, "taxes_category", "h2").await,
        antes_h2_cat,
        "🔴 FUGA ENTRE TENANTS: el reset de h1 se llevó categorías del hub h2"
    );
}

// ── 3. Las filas del módulo sobreviven ──────────────────────────────────────────────────

/// `taxes` siembra al instalarse sus categorías canónicas (`is_system=1`) y alias de fábrica
/// (`source='shipped'`), y NO las vuelve a sembrar. Si el reset se las lleva, el hub queda sin
/// IVA y sin forma de recuperarlo salvo reinstalando el módulo. El reset borra datos de USUARIO.
#[tokio::test]
async fn reset_conserva_las_filas_sembradas_por_el_modulo() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    rt.execute_command(
        "taxes.categories.create",
        &params(json!({ "key": "user.custom", "name": "Categoría del usuario" })),
        &ctx("h1"),
    )
    .await
    .expect("categoría de usuario");

    let sembradas_antes = count(&rt, "taxes_category", "h1").await - 1; // menos la de usuario
    assert!(sembradas_antes > 0, "precondición: instalar taxes siembra categorías is_system");

    execute_reset(&rt, "h1", &wipe_modules(), ACTOR).await.expect("reset");

    assert_eq!(
        count(&rt, "taxes_category", "h1").await,
        sembradas_antes,
        "las categorías del módulo (is_system=1) deben sobrevivir; solo se va la del usuario"
    );
    // Y la del usuario sí se fue.
    let mut p = Params::new();
    p.insert("hub_id".into(), json!("h1"));
    let res = rt
        .db()
        .query("SELECT key FROM taxes_category WHERE hub_id = :hub_id AND key = 'user.custom'", &p)
        .await
        .unwrap();
    assert!(res.rows.is_empty(), "la categoría creada por el usuario debe borrarse");
}

// ── 4. Orden inverso de FK ──────────────────────────────────────────────────────────────

/// `inventory_product_categories` es un vínculo M2M SIN `hub_id` propio, con FK a producto y a
/// categoría. Si el reset borra los productos ANTES que el vínculo, el DELETE revienta contra la
/// FK y el reset entero falla. Debe recorrerse en orden topológico inverso (hijos primero).
#[tokio::test]
async fn reset_borra_los_vinculos_m2m_antes_que_sus_padres() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;
    rt.execute_command(
        "inventory.categories.create",
        &params(json!({ "name": "Cafés", "slug": "cafes", "icon": "cube-outline",
                        "color": "#3880ff", "description": "", "order": 0 })),
        &ctx("h1"),
    )
    .await
    .expect("categoría");
    let prods = rt.execute_query("inventory.products.list", &Params::new(), &ctx("h1")).await.unwrap();
    let cats = rt.execute_query("inventory.categories.list", &Params::new(), &ctx("h1")).await.unwrap();
    rt.execute_command(
        "inventory.products.add_category",
        &params(json!({
            "product_id": prods[0]["id"].as_str().unwrap(),
            "category_id": cats[0]["id"].as_str().unwrap(),
        })),
        &ctx("h1"),
    )
    .await
    .expect("vincular producto↔categoría");
    assert_eq!(count_all(&rt, "inventory_product_categories").await, 1, "precondición: 1 vínculo");

    // Si el orden de borrado fuese el ingenuo, esto devolvería Err por violación de FK.
    execute_reset(&rt, "h1", &wipe_modules(), ACTOR).await.expect("el reset no puede romperse por una FK");

    assert_eq!(count(&rt, "inventory_product", "h1").await, 0, "productos borrados");
    assert_eq!(
        count_all(&rt, "inventory_product_categories").await,
        0,
        "el vínculo M2M debe irse con sus padres (si no, quedan filas huérfanas)"
    );
}

// ── 5. `plan_reset` es dry-run y cuenta de verdad ───────────────────────────────────────

/// La UI pinta CIFRAS («se borrarán 124 productos»), no adjetivos: el plan tiene que contar filas
/// reales. Y por ser dry-run, no puede borrar nada — se ejecuta solo con abrir el panel.
#[tokio::test]
async fn plan_reset_cuenta_filas_reales_y_no_borra_nada() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;
    create_product(&rt, "h1", "Té", "TEV").await;
    create_product(&rt, "h1", "Zumo", "ZUM").await;

    let plan = plan_reset(&rt, "h1").await.expect("plan");

    let inv = plan
        .sections
        .iter()
        .find(|s| s.section == "modules/inventory")
        .expect("el plan debe listar modules/inventory");
    assert!(
        inv.rows >= 3,
        "el plan debe contar las filas reales del hub (3 productos), trae {}",
        inv.rows
    );
    assert!(inv.blocked_by.is_none(), "sin facturas remitidas nada bloquea inventory");
    // Dry-run: nada se ha tocado.
    assert_eq!(count(&rt, "inventory_product", "h1").await, 3, "plan_reset NO puede borrar");
}

/// El plan cuenta lo del hub que pregunta, no lo del vecino (misma BD, distinto tenant).
#[tokio::test]
async fn plan_reset_no_cuenta_filas_de_otro_hub() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;
    for (i, sku) in ["A", "B", "C", "D"].iter().enumerate() {
        create_product(&rt, "h2", &format!("Ajeno {i}"), sku).await;
    }

    let plan = plan_reset(&rt, "h1").await.expect("plan");
    let inv = plan.sections.iter().find(|s| s.section == "modules/inventory").unwrap();

    assert_eq!(inv.rows, 1, "el plan de h1 cuenta 1 producto, no los 4 del vecino (trae {})", inv.rows);
}

// ── 6. Selectividad ─────────────────────────────────────────────────────────────────────

/// Un módulo no seleccionado no se toca: el usuario que solo quiere limpiar el catálogo de demo
/// no puede perder, de paso, su configuración fiscal.
#[tokio::test]
async fn reset_solo_toca_las_secciones_seleccionadas() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    create_product(&rt, "h1", "Café", "CAF").await;
    rt.execute_command(
        "taxes.categories.create",
        &params(json!({ "key": "user.custom", "name": "Del usuario" })),
        &ctx("h1"),
    )
    .await
    .expect("categoría de usuario");
    let taxes_antes = count(&rt, "taxes_category", "h1").await;

    // Solo inventory.
    let sel = ResetSelection { modules: vec!["inventory".into()], ..Default::default() };
    execute_reset(&rt, "h1", &sel, ACTOR).await.expect("reset parcial");

    assert_eq!(count(&rt, "inventory_product", "h1").await, 0, "inventory sí se borra");
    assert_eq!(
        count(&rt, "taxes_category", "h1").await,
        taxes_antes,
        "taxes NO estaba seleccionado: no se puede tocar"
    );
}

// ── 7. No te puedes auto-expulsar ───────────────────────────────────────────────────────

/// Garantía del ADR-0170: el reset nunca borra al usuario que lo ejecuta. Si lo hiciera, un
/// owner podría quedarse fuera de su propio hub con un clic y sin vuelta atrás.
#[tokio::test]
async fn reset_de_usuarios_conserva_a_quien_lo_ejecuta() {
    if !have_modules() { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    let rt = fresh().await;
    let db = rt.db();
    let owner = erplora_runtime::identity::create_user(db, "Dueño", "1234", "owner", None)
        .await
        .expect("crear owner");
    let empleado = erplora_runtime::identity::create_user(db, "Empleado", "5678", "cashier", None)
        .await
        .expect("crear empleado");

    let sel = ResetSelection { users: true, ..Default::default() };
    execute_reset(&rt, "h1", &sel, &owner).await.expect("reset de usuarios");

    let res = rt.db().query("SELECT id FROM hub_user", &Params::new()).await.unwrap();
    let ids: Vec<String> =
        res.rows.iter().filter_map(|r| r["id"].as_str().map(str::to_string)).collect();
    assert!(ids.contains(&owner), "🔴 el reset expulsó al usuario que lo ejecutaba");
    assert!(!ids.contains(&empleado), "el resto de empleados sí se borran cuando se marca la sección");
}
