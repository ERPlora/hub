//! ADR-0147 — cantidades en punto fijo (escala global 10⁶) + registro de unidades, en `inventory`.
//!
//! El contrato que fijan estos tests:
//!
//! * el hub trae un **registro de unidades** sembrado (`ud`, `kg`/`g`/`t`, `l`/`ml`, `min`/`h`),
//!   cada una con su factor como **fracción exacta** y su **incremento**;
//! * el producto declara su **unidad base de inventario**; sin declararla es `ud`;
//! * las cantidades viajan y se guardan en **escala 10⁶**: 0,5 kg es `500000`;
//! * el **incremento se valida**: fuera de rejilla el comando se **rechaza**, no se redondea;
//! * el precio es **importe entero por cantidad de precio** (KPEIN): «0,37 € por 100 ud».
//!
//! De dónde sale: `as_i64(0.5)` = 0 y `decrease_on_sale` hacía `qty <= 0 → continue`, así que
//! vender al peso **no descontaba stock y nadie se enteraba**.

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

/// Escala global de cantidades (ADR-0147 §2.1). Duplicada aquí a propósito: si alguien la cambia
/// en el SDK, estos tests tienen que fallar y obligar a mirar la migración.
const SCALE: i64 = 1_000_000;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules").join(name)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}
fn wasm_present() -> bool {
    mdir("inventory").join("dist/handler.wasm").exists()
}

async fn fresh() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.install_from_dir(&mdir("taxes")).await.expect("instalar taxes");
    rt.install_from_dir(&mdir("inventory")).await.expect("instalar inventory");
    rt
}

/// Alta de producto; `unit` ausente → la unidad por defecto.
async fn producto(rt: &Runtime, ctx: &RequestContext, name: &str, unit: Option<&str>) -> String {
    let mut p = json!({ "name": name, "sku": name.to_lowercase(), "price": 1200, "stock": 0 });
    if let Some(u) = unit {
        p["unit_code"] = json!(u);
    }
    let res = rt.execute_command("inventory.products.create", &params(p), ctx).await.unwrap();
    res["new_ids"][0].as_str().unwrap().to_string()
}

async fn stock_de(rt: &Runtime, ctx: &RequestContext, id: &str) -> i64 {
    let filas = rt
        .execute_query("inventory.products.get", &params(json!({ "product_id": id })), ctx)
        .await
        .unwrap();
    filas[0]["stock"].as_i64().expect("el stock es un entero en escala 10⁶")
}

// ── El registro de unidades ─────────────────────────────────────────────────────────────
#[tokio::test]
async fn el_hub_trae_un_registro_de_unidades_sembrado() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    let rt = fresh().await;
    let ctx = admin();
    let unidades = rt.execute_query("inventory.units.list", &Params::new(), &ctx).await.unwrap();

    let por_codigo = |c: &str| unidades.iter().find(|u| u["code"] == json!(c)).cloned();

    // La unidad suelta: escalón de 1, no se parte.
    let ud = por_codigo("ud").expect("la unidad suelta está sembrada");
    assert_eq!(ud["increment_value"].as_i64(), Some(SCALE), "una pieza no se parte");

    // El kilo: escalón de gramo, que es lo que da una báscula de mostrador.
    let kg = por_codigo("kg").expect("el kilo está sembrado");
    assert_eq!(kg["increment_value"].as_i64(), Some(1_000), "0,001 kg = 1 g");

    // La hora se factura en cuartos — el caso que justifica separar escala e incremento.
    let h = por_codigo("h").expect("la hora está sembrada");
    assert_eq!(h["increment_value"].as_i64(), Some(250_000), "0,25 h");

    // El factor es una FRACCIÓN EXACTA, no un decimal: 1 h = 60/1 min.
    assert_eq!(h["factor_num"].as_i64(), Some(60));
    assert_eq!(h["factor_den"].as_i64(), Some(1));
}

#[tokio::test]
async fn el_producto_declara_su_unidad_base_y_sin_declararla_es_ud() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    let rt = fresh().await;
    let ctx = admin();
    let gambas = producto(&rt, &ctx, "Gambas", Some("kg")).await;
    let cana = producto(&rt, &ctx, "Cana", None).await;

    let g = rt
        .execute_query("inventory.products.get", &params(json!({ "product_id": gambas })), &ctx)
        .await
        .unwrap();
    assert_eq!(g[0]["unit_code"], json!("kg"), "las gambas se venden al peso");

    let c = rt
        .execute_query("inventory.products.get", &params(json!({ "product_id": cana })), &ctx)
        .await
        .unwrap();
    // El caso mayoritario no obliga a declarar nada: un bar vende cañas, no kilos de caña.
    assert_eq!(c[0]["unit_code"], json!("ud"), "sin declarar, unidad suelta");
}

// ── Cantidades en escala 10⁶ ────────────────────────────────────────────────────────────
#[tokio::test]
async fn media_racion_de_gambas_si_descuenta_stock() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    let rt = fresh().await;
    let ctx = admin();
    let gambas = producto(&rt, &ctx, "Gambas", Some("kg")).await;

    // 2,5 kg
    rt.execute_command(
        "inventory.stock.receive",
        &params(json!({ "items": [{ "product_id": gambas, "qty": 2_500_000 }] })),
        &ctx,
    )
    .await
    .expect("recibir 2,5 kg");
    assert_eq!(stock_de(&rt, &ctx, &gambas).await, 2_500_000);

    // 0,5 kg — el caso que antes se truncaba a 0 y no descontaba nada.
    rt.execute_command(
        "inventory.stock.decrease",
        &params(json!({ "product_id": gambas, "qty": 500_000 })),
        &ctx,
    )
    .await
    .expect("vender medio kilo");
    assert_eq!(stock_de(&rt, &ctx, &gambas).await, 2_000_000, "quedan 2 kg");
}

#[tokio::test]
async fn el_libro_de_movimientos_va_en_la_misma_escala() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // El ledger es la fuente de verdad del saldo (#7): en otra escala, el saldo reconstruido no
    // cuadraría con la proyección del producto.
    let rt = fresh().await;
    let ctx = admin();
    let gambas = producto(&rt, &ctx, "Gambas", Some("kg")).await;
    rt.execute_command(
        "inventory.stock.receive",
        &params(json!({ "items": [{ "product_id": gambas, "qty": 500_000 }] })),
        &ctx,
    )
    .await
    .unwrap();

    let movs = rt.execute_query("inventory.stock.movements", &Params::new(), &ctx).await.unwrap();
    let recepcion = movs
        .iter()
        .find(|m| m["movement_type"] == json!("reception"))
        .expect("hay movimiento de recepción");
    assert_eq!(recepcion["qty"].as_i64(), Some(500_000), "el delta, en escala 10⁶");
    assert_eq!(recepcion["stock_after"].as_i64(), Some(500_000), "y el saldo también");
}

// ── El incremento se VALIDA, no se redondea ─────────────────────────────────────────────
#[tokio::test]
async fn una_cantidad_fuera_de_la_rejilla_se_rechaza() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // ADR-0147 §2.2: medio gramo en un producto con escalón de gramo NO se redondea en silencio.
    // Aceptarlo modificaría calladamente el stock y las estadísticas.
    let rt = fresh().await;
    let ctx = admin();
    let gambas = producto(&rt, &ctx, "Gambas", Some("kg")).await;
    rt.execute_command(
        "inventory.stock.receive",
        &params(json!({ "items": [{ "product_id": gambas, "qty": 1_000_000 }] })),
        &ctx,
    )
    .await
    .unwrap();

    let r = rt
        .execute_command(
            "inventory.stock.decrease",
            &params(json!({ "product_id": gambas, "qty": 500 })), // 0,0005 kg = medio gramo
            &ctx,
        )
        .await;
    assert!(r.is_err(), "medio gramo no cae en la rejilla de gramos: {r:?}");
    assert_eq!(stock_de(&rt, &ctx, &gambas).await, 1_000_000, "y el stock NO se ha tocado");
}

// ── La unidad maestra se puede cambiar (y no se pierde) por update ──────────────────────
#[tokio::test]
async fn la_unidad_maestra_se_puede_cambiar_por_update() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // Incidencia: el schema de `products.update` llevaba `additionalProperties: false` y
    // rechazaba `unit_code` — la unidad maestra quedaba grabada a fuego en el alta.
    let rt = fresh().await;
    let ctx = admin();
    let gambas = producto(&rt, &ctx, "Gambas", Some("kg")).await;

    // update es un REEMPLAZO completo (#178) para lo obligatorio… pero la unidad es
    // ADITIVA a propósito: un caller pre-0147 que no la envíe NO la borra.
    rt.execute_command(
        "inventory.products.update",
        &params(json!({
            "product_id": gambas, "name": "Gambas", "price": 1200, "cost": 0,
            "low_stock_threshold": 5, "is_active": 1, "ean13": null, "description": ""
        })),
        &ctx,
    )
    .await
    .expect("update sin unit_code");
    let g = rt
        .execute_query("inventory.products.get", &params(json!({ "product_id": gambas })), &ctx)
        .await
        .unwrap();
    assert_eq!(g[0]["unit_code"], json!("kg"), "sin enviarla, la unidad se CONSERVA");

    // Cambiarla es un acto explícito: enviar `unit_code` en el update.
    rt.execute_command(
        "inventory.products.update",
        &params(json!({
            "product_id": gambas, "name": "Gambas", "price": 1200, "cost": 0,
            "low_stock_threshold": 5, "is_active": 1, "ean13": null, "description": "",
            "unit_code": "ud"
        })),
        &ctx,
    )
    .await
    .expect("update con unit_code: la unidad maestra se puede cambiar");
    let g = rt
        .execute_query("inventory.products.get", &params(json!({ "product_id": gambas })), &ctx)
        .await
        .unwrap();
    assert_eq!(g[0]["unit_code"], json!("ud"), "la unidad maestra cambió a ud");
}

// ── Precio: importe entero por cantidad de precio (KPEIN) ───────────────────────────────
#[tokio::test]
async fn un_precio_sub_centimo_se_guarda_como_importe_por_cien_unidades() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // 0,0037 €/ud no es un entero de céntimos. En vez de meter decimales en el dinero —lo que
    // tocaría la frontera fiscal— se guarda «0,37 € por 100 ud» (ADR-0147 §2.3).
    let rt = fresh().await;
    let ctx = admin();
    let res = rt
        .execute_command(
            "inventory.products.create",
            &params(json!({
                "name": "Tornillo", "sku": "TOR", "stock": 0,
                "price": 37, "price_quantity_value": 100 * SCALE, "pricing_unit_code": "ud"
            })),
            &ctx,
        )
        .await
        .expect("alta con precio por 100 unidades");
    let id = res["new_ids"][0].as_str().unwrap();

    let p = rt
        .execute_query("inventory.products.get", &params(json!({ "product_id": id })), &ctx)
        .await
        .unwrap();
    assert_eq!(p[0]["price"].as_i64(), Some(37), "el dinero sigue siendo entero de céntimos");
    assert_eq!(p[0]["price_quantity_value"].as_i64(), Some(100 * SCALE), "por 100 ud");
    assert_eq!(p[0]["pricing_unit_code"], json!("ud"));
}

#[tokio::test]
async fn por_defecto_el_precio_es_por_una_unidad() {
    if !std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
        .join("../../../modules-workspace/modules").exists()
    { eprintln!("SKIP: modules-workspace not present (CI)"); return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // El comportamiento de siempre no cambia: quien no configure nada tiene «X € por 1 ud».
    let rt = fresh().await;
    let ctx = admin();
    let cana = producto(&rt, &ctx, "Cana", None).await;
    let p = rt
        .execute_query("inventory.products.get", &params(json!({ "product_id": cana })), &ctx)
        .await
        .unwrap();
    assert_eq!(p[0]["price_quantity_value"].as_i64(), Some(SCALE), "por 1 unidad");
    assert_eq!(p[0]["pricing_unit_code"], json!("ud"));
}
