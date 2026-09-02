//! E2E ROJOS (TDD, ADR-0170 Fase 3) de DESHACER UNA IMPORTACIÓN.
//!
//! Es el camino que motiva todo el ADR: **importo la demo → la miro → la quito limpiamente →
//! cargo mis datos**. El reset por secciones no vale aquí, porque para entonces el usuario ya ha
//! creado cosas suyas y borrar «el módulo entero» se las llevaría por delante.
//!
//! Mecánica: el import registra en `_hub_import_batch` / `_hub_import_row` **qué filas insertó de
//! verdad** (vía `RETURNING id`, así las que el guard `NOT EXISTS` descartó no se apuntan), y
//! deshacer borra exactamente esas — nada más.
//!
//! Contrato que fijan estos tests:
//!   - deshacer borra lo que trajo el blueprint,
//!   - **NO toca lo que el usuario creó después** (esta es la garantía que lo diferencia del
//!     reset por secciones),
//!   - deshacer dos veces no rompe (idempotente),
//!   - el lote es por hub: deshacer el del hub A no toca al hub B.

use std::path::PathBuf;

use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::reset::{list_import_batches, undo_import};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

/// Same resolution as the `require_modules_workspace` guard — it honours `$ERPLORA_MODULES_DIR`.
fn modules_root() -> PathBuf {
    erplora_runtime::e2e_support::modules_root()
}

fn ctx(hub: &str) -> RequestContext {
    RequestContext::new(hub, "u1", ["*".to_string()])
}

async fn fresh() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&modules_root().join("taxes"))
        .await
        .expect("instalar taxes");
    rt.install_from_dir(&modules_root().join("inventory"))
        .await
        .expect("instalar inventory");
    rt
}

async fn count(rt: &Runtime, table: &str, hub: &str) -> i64 {
    let mut p = Params::new();
    p.insert("hub_id".into(), json!(hub));
    let res = rt
        .db()
        .query(
            &format!("SELECT count(*) AS n FROM {table} WHERE hub_id = :hub_id"),
            &p,
        )
        .await
        .unwrap_or_else(|e| panic!("contar {table}: {e}"));
    res.rows[0]["n"].as_i64().expect("count(*)")
}

/// SQL de un blueprint de demo: dos productos, con el placeholder de tenant del export
/// (`__HUB_ID__`) y el guard de idempotencia real.
fn demo_sql() -> String {
    ["demo-prod-1", "demo-prod-2"]
        .iter()
        .enumerate()
        .map(|(i, id)| {
            format!(
                "INSERT INTO inventory_product (id, hub_id, name, sku, price, cost, stock, created_at) \
                 SELECT '{id}', '__HUB_ID__', 'Demo {i}', 'DEMO{i}', 100, 50, 5, '2026-07-31T10:00:00Z' \
                 WHERE NOT EXISTS (SELECT 1 FROM inventory_product WHERE id = '{id}');\n"
            )
        })
        .collect()
}

/// Aplica un blueprint REGISTRANDO el lote (lo que hace el import tras ADR-0170).
async fn import_demo(rt: &Runtime, hub: &str, name: &str) -> String {
    // Mismo scope que usaría el import real para `data/inventory.sql`: el trazado NO puede
    // ejecutar SQL que el import rechazaría.
    let scope = erplora_runtime::import_sql::scope_for_data_file("data/inventory.sql")
        .expect("scope de la sección inventory");
    erplora_runtime::reset::apply_tracked(rt, hub, name, &demo_sql(), &scope)
        .await
        .expect("importar el blueprint registrando el lote")
}

// ── El caso que motiva el ADR ───────────────────────────────────────────────────────────

#[tokio::test]
async fn deshacer_una_importacion_borra_solo_lo_que_trajo() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = fresh().await;
    let batch = import_demo(&rt, "h1", "restaurante_es").await;
    assert_eq!(
        count(&rt, "inventory_product", "h1").await,
        2,
        "precondición: la demo entró"
    );

    // El usuario prueba la demo y AÑADE lo suyo.
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Mi producto", "sku": "MIO", "price": 900, "cost": 400, "stock": 3, "tax_category_key": "product.generic" })),
        &ctx("h1"),
    )
    .await
    .expect("producto del usuario");
    assert_eq!(count(&rt, "inventory_product", "h1").await, 3);

    undo_import(&rt, "h1", &batch)
        .await
        .expect("deshacer la importación");

    // Se va la demo; sobrevive lo del usuario. ESTA es la diferencia con el reset por secciones.
    assert_eq!(
        count(&rt, "inventory_product", "h1").await,
        1,
        "deshacer debe llevarse los 2 de la demo y NO el del usuario"
    );
    let res = rt
        .db()
        .query("SELECT sku FROM inventory_product", &Params::new())
        .await
        .unwrap();
    let skus: Vec<&str> = res.rows.iter().filter_map(|r| r["sku"].as_str()).collect();
    assert_eq!(
        skus,
        vec!["MIO"],
        "lo que queda debe ser exactamente lo del usuario: {skus:?}"
    );
}

/// Deshacer dos veces no puede reventar ni llevarse nada de más: el usuario puede pulsar dos
/// veces, o reintentar tras un error de red.
#[tokio::test]
async fn deshacer_dos_veces_es_idempotente() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = fresh().await;
    let batch = import_demo(&rt, "h1", "restaurante_es").await;

    undo_import(&rt, "h1", &batch)
        .await
        .expect("primer deshacer");
    undo_import(&rt, "h1", &batch)
        .await
        .expect("segundo deshacer: no puede fallar");

    assert_eq!(count(&rt, "inventory_product", "h1").await, 0);
}

/// El lote pertenece a un hub: deshacer el de h1 no puede tocar las filas de h2 (misma BD).
#[tokio::test]
async fn deshacer_un_lote_no_toca_otro_hub() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = fresh().await;
    let batch_h1 = import_demo(&rt, "h1", "restaurante_es").await;
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Del vecino", "sku": "VEC", "price": 100, "cost": 50, "stock": 1, "tax_category_key": "product.generic" })),
        &ctx("h2"),
    )
    .await
    .expect("producto del vecino");

    undo_import(&rt, "h1", &batch_h1)
        .await
        .expect("deshacer h1");

    assert_eq!(
        count(&rt, "inventory_product", "h1").await,
        0,
        "h1 deshecho"
    );
    assert_eq!(
        count(&rt, "inventory_product", "h2").await,
        1,
        "🔴 el vecino perdió datos"
    );
}

/// El panel lista las importaciones para que el usuario elija cuál deshacer.
#[tokio::test]
async fn las_importaciones_se_listan_por_hub() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = fresh().await;
    import_demo(&rt, "h1", "restaurante_es").await;
    import_demo(&rt, "h2", "barberia_es").await;

    let batches = list_import_batches(&rt, "h1").await.expect("listar lotes");

    assert_eq!(batches.len(), 1, "solo el lote de h1: {batches:?}");
    assert_eq!(batches[0].name, "restaurante_es");
    assert_eq!(batches[0].rows, 2, "el lote debe saber cuántas filas trajo");
}

/// Re-importar el MISMO blueprint no duplica (guard `NOT EXISTS`), así que el segundo lote no
/// puede apuntarse filas que no insertó — si lo hiciera, deshacerlo borraría las del primero.
#[tokio::test]
async fn un_lote_solo_registra_las_filas_que_realmente_inserto() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = fresh().await;
    let primero = import_demo(&rt, "h1", "restaurante_es").await;
    let segundo = import_demo(&rt, "h1", "restaurante_es_otra_vez").await;

    let batches = list_import_batches(&rt, "h1").await.expect("listar");
    let segundo_lote = batches
        .iter()
        .find(|b| b.id == segundo)
        .expect("el segundo lote existe");
    assert_eq!(
        segundo_lote.rows, 0,
        "el re-import no insertó nada: no puede apuntarse filas"
    );

    // Y deshacer el segundo no puede llevarse lo que trajo el primero.
    undo_import(&rt, "h1", &segundo)
        .await
        .expect("deshacer el segundo");
    assert_eq!(
        count(&rt, "inventory_product", "h1").await,
        2,
        "la demo del primer lote sigue"
    );

    undo_import(&rt, "h1", &primero)
        .await
        .expect("deshacer el primero");
    assert_eq!(count(&rt, "inventory_product", "h1").await, 0);
}

// ── Integración con el import REAL (no solo el motor suelto) ────────────────────────────

/// El camino completo: exportar de A → **importar en B con `import_sections`** → el lote queda
/// registrado y se puede deshacer. Sin esto, el motor de lotes existe pero nadie lo alimenta:
/// es la diferencia entre «implementado» y «disponible».
#[tokio::test]
async fn el_import_real_registra_un_lote_deshacible() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    // Hub A con datos → bundle.
    let a = fresh().await;
    for (name, sku) in [("Café", "CAF"), ("Té verde", "TEV")] {
        a.execute_command(
            "inventory.products.create",
            &params(json!({ "name": name, "sku": sku, "price": 450, "cost": 200, "stock": 10, "tax_category_key": "product.generic" })),
            &ctx("h1"),
        )
        .await
        .expect("producto en A");
    }
    let bundle = erplora_runtime::export::export_hub(
        &a,
        "h1",
        &erplora_runtime::export::ExportSelection {
            users: false,
            settings: false,
            settings_items: None,
            fiscal: false,
            media: false,
            modules: vec![erplora_runtime::export::ModuleDataSelection {
                module_id: "inventory".into(),
                with_data: true,
                tables: None,
            }],
            purpose: Default::default(),
        },
        "restaurante",
        "es",
        "2026-07-31T10:00:00Z",
    )
    .await
    .expect("export de A");

    // Hub destino B (tenant h2) — el flujo real del import.
    let mut b = fresh().await;
    erplora_runtime::import::import_sections(
        &mut b,
        &bundle.manifest,
        &bundle.files,
        &erplora_runtime::import::ImportSelection {
            users: false,
            settings: false,
            fiscal: false,
            media: false,
            modules: vec!["inventory".into()],
        },
        "h2",
    )
    .await
    .expect("import en B");

    assert_eq!(
        count(&b, "inventory_product", "h2").await,
        2,
        "precondición: la demo entró en B"
    );

    // El import dejó UN lote, con el nombre del blueprint y sus filas.
    let batches = list_import_batches(&b, "h2")
        .await
        .expect("listar lotes tras el import real");
    assert_eq!(
        batches.len(),
        1,
        "el import real debe registrar un lote: {batches:?}"
    );
    assert_eq!(
        batches[0].name, "restaurante",
        "el lote toma el nombre del manifest"
    );
    assert_eq!(
        batches[0].rows, 2,
        "el lote debe apuntar las 2 filas insertadas"
    );

    // Y el usuario añade lo suyo DESPUÉS.
    b.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Mío", "sku": "MIO", "price": 900, "cost": 400, "stock": 1, "tax_category_key": "product.generic" })),
        &ctx("h2"),
    )
    .await
    .expect("producto del usuario en B");

    undo_import(&b, "h2", &batches[0].id)
        .await
        .expect("deshacer el import real");

    assert_eq!(
        count(&b, "inventory_product", "h2").await,
        1,
        "deshacer se lleva la demo importada y conserva lo del usuario"
    );
}
