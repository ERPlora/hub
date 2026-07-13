//! E2E real del módulo `inventory` (portado de modules/m_inventory): instala el
//! módulo real desde `modules/inventory` (con su `dist/handler.wasm` compilado)
//! y ejercita CRUD declarativo + los dos handlers WASM batch (bulk_create,
//! receive_stock) contra SQLite en memoria.
//!
//! Si `dist/handler.wasm` no existe (no se compiló el guest), se salta con aviso.
use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn inventory_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules/inventory")
}

fn admin_ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

fn wasm_present() -> bool {
    inventory_dir().join("dist/handler.wasm").exists()
}

async fn fresh() -> Runtime {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    // inventory depende de taxes (ADR-0066): instalar taxes primero.
    rt.install_from_dir(&inventory_dir().parent().unwrap().join("taxes")).await.expect("instalar taxes");
    rt.install_from_dir(&inventory_dir()).await.expect("instalar inventory");
    rt
}

#[tokio::test]
async fn install_registers_capabilities() {
    let rt = fresh().await;
    let reg = rt.registry();
    assert!(reg.is_installed("inventory"));
    assert!(reg.get_query("inventory.products.list").is_some());
    assert!(reg.get_command("inventory.products.create").is_some());
    assert!(reg.get_command("inventory.products.bulk_create").is_some());
    assert!(reg.get_command("inventory.stock.receive").is_some());
    // El listener de sale.completed mapea al handler WASM que expande las líneas
    // del ticket en N bajas de stock (contrato cross-módulo).
    assert_eq!(reg.listeners_for("sale.completed"), ["inventory.stock.decrease_on_sale"]);
}

#[tokio::test]
async fn product_crud_and_low_stock() {
    let rt = fresh().await;
    let ctx = admin_ctx();

    rt.execute_command(
        "inventory.products.create",
        &params(json!({
            "name": "Café", "sku": "CAF", "price": 450, "cost": 200,
            "stock": 3, "low_stock_threshold": 5, "product_type": "physical",
            "ean13": null, "description": "", "tax_category_key": null, "image": ""
        })),
        &ctx,
    ).await
    .unwrap();

    let rows = rt.execute_query("inventory.products.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(rows.len(), 1);
    assert_eq!(rows[0]["name"], json!("Café"));

    // stock 3 <= threshold 5 → aparece en low_stock.
    let low = rt.execute_query("inventory.products.low_stock", &Params::new(), &ctx).await.unwrap();
    assert_eq!(low.len(), 1);

    // stats: 1 producto, en stock, valor 450 céntimos × 3 = 1350 céntimos (13.50€).
    let stats = rt.execute_query("inventory.products.stats", &Params::new(), &ctx).await.unwrap();
    assert_eq!(stats[0]["total_products"], json!(1));
    assert_eq!(stats[0]["total_inventory_value"].as_i64().unwrap(), 1350);

    // Otro hub no ve nada (scope hub_id).
    let other = RequestContext::new("h2", "u9", ["*".to_string()]);
    let rows2 = rt.execute_query("inventory.products.list", &Params::new(), &other).await.unwrap();
    assert_eq!(rows2.len(), 0);
}

#[tokio::test]
async fn stock_adjust_clamps_at_zero() {
    let rt = fresh().await;
    let ctx = admin_ctx();
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "X", "sku": "X1", "price": 1, "cost": 0, "stock": 2,
                        "low_stock_threshold": 10, "product_type": "physical",
                        "ean13": null, "description": "", "tax_category_key": null, "image": "" })),
        &ctx,
    ).await.unwrap();
    let id = rt.execute_query("inventory.products.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    // -5 sobre stock 2 → MAX(0, -3) = 0 (no negativo por defecto).
    rt.execute_command("inventory.stock.adjust",
        &params(json!({ "product_id": id, "delta": -5 })), &ctx).await.unwrap();
    let p = rt.execute_query("inventory.products.get", &params(json!({"product_id": id})), &ctx).await.unwrap();
    assert_eq!(p[0]["stock"], json!(0));
}

#[tokio::test]
async fn bulk_create_wasm_inserts_with_generated_skus() {
    if !wasm_present() {
        eprintln!("SKIP: modules/inventory/dist/handler.wasm no existe");
        return;
    }
    let rt = fresh().await;
    let ctx = admin_ctx();
    let res = rt
        .execute_command(
            "inventory.products.bulk_create",
            &params(json!({
                "existing_count": 0,
                "products": [
                    { "name": "Café", "price": 450 },
                    { "name": "Té", "sku": "TE-1", "price": 300, "stock": 20 },
                    { "name": "Agua", "price": 100 }
                ]
            })),
            &ctx,
        ).await
        .expect("bulk_create ejecuta el handler WASM");
    assert_eq!(res["operations"], json!(3));

    let rows = rt.execute_query("inventory.products.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(rows.len(), 3);
    let skus: Vec<String> = rows.iter().map(|r| r["sku"].as_str().unwrap().to_string()).collect();
    // SKUs autogenerados PROD-001/PROD-003 + el explícito TE-1.
    assert!(skus.contains(&"PROD-001".to_string()), "skus={skus:?}");
    assert!(skus.contains(&"TE-1".to_string()), "skus={skus:?}");
    assert!(skus.contains(&"PROD-003".to_string()), "skus={skus:?}");
}

#[tokio::test]
async fn receive_stock_wasm_increments_existing() {
    if !wasm_present() {
        eprintln!("SKIP: handler.wasm no existe");
        return;
    }
    let rt = fresh().await;
    let ctx = admin_ctx();
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Café", "sku": "CAF", "price": 450, "cost": 200, "stock": 10,
                        "low_stock_threshold": 5, "product_type": "physical",
                        "ean13": null, "description": "", "tax_category_key": null, "image": "" })),
        &ctx,
    ).await.unwrap();
    let id = rt.execute_query("inventory.products.list", &Params::new(), &ctx).await.unwrap()[0]["id"]
        .as_str().unwrap().to_string();

    // Recibe 25 unidades + actualiza coste a 2.5.
    let res = rt.execute_command(
        "inventory.stock.receive",
        &params(json!({ "items": [{ "product_id": id, "qty": 25, "unit_cost": 250 }] })),
        &ctx,
    ).await.expect("receive_stock WASM");
    assert_eq!(res["operations"], json!(1));

    let p = rt.execute_query("inventory.products.get", &params(json!({"product_id": id})), &ctx).await.unwrap();
    assert_eq!(p[0]["stock"], json!(35)); // 10 + 25
    assert_eq!(p[0]["cost"], json!(250)); // 2.50€ en céntimos
}

#[tokio::test]
async fn category_crud() {
    let rt = fresh().await;
    let ctx = admin_ctx();
    rt.execute_command(
        "inventory.categories.create",
        &params(json!({ "name": "Bebidas", "slug": "bebidas", "icon": "cube-outline",
                        "color": "#3880ff", "description": "", "order": 0 })),
        &ctx,
    ).await.unwrap();
    let cats = rt.execute_query("inventory.categories.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(cats.len(), 1);
    assert_eq!(cats[0]["name"], json!("Bebidas"));
    assert_eq!(cats[0]["product_count"], json!(0));
}

/// Vínculo producto↔categoría (M2M `inventory_product_categories`). La tabla y sus lectores ya
/// existían — el TPV pide `inventory.product_categories` para filtrar la carta por categoría y
/// `categories.list` cuenta productos por esa M2M — pero ningún comando la escribía: no había
/// forma de asignarle una categoría a un producto. Contrato: escalar, idempotente y acotado al
/// hub del contexto (la tabla es un join puro, sin `hub_id` propio → la guarda la pone el SQL).
#[tokio::test]
async fn product_category_link_add_and_remove() {
    let rt = fresh().await;
    let ctx = admin_ctx();

    rt.execute_command(
        "inventory.categories.create",
        &params(json!({ "name": "Cafés e infusiones", "slug": "cafes", "icon": "cafe-outline",
                        "color": "#3880ff", "description": "", "order": 0 })),
        &ctx,
    ).await.unwrap();
    let cats = rt.execute_query("inventory.categories.list", &Params::new(), &ctx).await.unwrap();
    let cat_id = cats[0]["id"].as_str().unwrap().to_string();

    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Café solo", "sku": "CAFE-SOLO", "price": 180, "cost": 0,
                        "stock": 0, "low_stock_threshold": 10, "product_type": "physical",
                        "ean13": null, "description": "", "tax_category_key": null, "image": "" })),
        &ctx,
    ).await.unwrap();
    let prods = rt.execute_query("inventory.products.list", &Params::new(), &ctx).await.unwrap();
    let prod_id = prods[0]["id"].as_str().unwrap().to_string();

    // Punto de partida: sin vínculo, el TPV no puede agrupar por categoría.
    let map = rt.execute_query("inventory.product_categories", &Params::new(), &ctx).await.unwrap();
    assert!(map.is_empty());

    rt.execute_command(
        "inventory.products.add_category",
        &params(json!({ "product_id": prod_id, "category_id": cat_id })),
        &ctx,
    ).await.unwrap();

    let map = rt.execute_query("inventory.product_categories", &Params::new(), &ctx).await.unwrap();
    assert_eq!(map.len(), 1);
    assert_eq!(map[0]["product_id"], json!(prod_id));
    assert_eq!(map[0]["category_id"], json!(cat_id));

    // El conteo de la lista de categorías (lo que pinta la UI) ve el vínculo.
    let cats = rt.execute_query("inventory.categories.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(cats[0]["product_count"], json!(1));

    // Idempotente: re-asignar no duplica ni revienta contra la PK compuesta.
    rt.execute_command(
        "inventory.products.add_category",
        &params(json!({ "product_id": prod_id, "category_id": cat_id })),
        &ctx,
    ).await.unwrap();
    let map = rt.execute_query("inventory.product_categories", &Params::new(), &ctx).await.unwrap();
    assert_eq!(map.len(), 1);

    // Un hub ajeno no puede ligar un producto que no es suyo (scoping por hub_id, §2.5).
    let other = RequestContext::new("h2", "u2", ["*".to_string()]);
    rt.execute_command(
        "inventory.products.add_category",
        &params(json!({ "product_id": prod_id, "category_id": cat_id })),
        &other,
    ).await.unwrap();
    let map = rt.execute_query("inventory.product_categories", &Params::new(), &ctx).await.unwrap();
    assert_eq!(map.len(), 1, "el hub ajeno no debe haber añadido nada");

    rt.execute_command(
        "inventory.products.remove_category",
        &params(json!({ "product_id": prod_id, "category_id": cat_id })),
        &ctx,
    ).await.unwrap();
    let map = rt.execute_query("inventory.product_categories", &Params::new(), &ctx).await.unwrap();
    assert!(map.is_empty());
}
