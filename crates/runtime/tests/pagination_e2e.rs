//! E2E del motor de listas (paginación + búsqueda + orden por whitelist + filtro por columna).
//! Usa el bloque `list` real de `inventory.products.list` sobre SQLite en memoria.
use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn mdir(n: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(n)
}

fn ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn fresh_with_products(names_prices: &[(&str, f64)]) -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("taxes")).await.expect("instalar taxes"); // inventory depends_on taxes (ADR-0066)
    rt.install_from_dir(&mdir("inventory")).await.expect("instalar inventory");
    for (i, (name, price)) in names_prices.iter().enumerate() {
        rt.execute_command(
            "inventory.products.create",
            &params(json!({
                "name": name, "sku": format!("SKU-{i}"), "price": price, "cost": 0,
                "stock": (i as i64) + 1, "low_stock_threshold": 5, "product_type": "physical",
                "ean13": null, "description": "", "tax_category_key": "product.generic", "image": ""
            })),
            &ctx(),
        )
        .await
        .unwrap();
    }
    rt
}

#[tokio::test]
async fn paginates_with_total() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let data = [("A", 1.0), ("B", 2.0), ("C", 3.0), ("D", 4.0), ("E", 5.0)];
    let rt = fresh_with_products(&data).await;

    // Página 1: limit 2, offset 0.
    let p1 = rt
        .execute_query_page("inventory.products.list", &params(json!({"limit": 2, "offset": 0})), &ctx())
        .await
        .unwrap();
    assert_eq!(p1.total, 5, "total = todas las filas filtradas, no la página");
    assert_eq!(p1.rows.len(), 2);
    assert_eq!(p1.limit, 2);
    assert_eq!(p1.offset, 0);
    // default_sort = name ASC.
    assert_eq!(p1.rows[0]["name"], json!("A"));
    assert_eq!(p1.rows[1]["name"], json!("B"));
    // `_total` no debe filtrarse a las filas.
    assert!(p1.rows[0].get("_total").is_none(), "_total se quita de cada fila");

    // Página 3 (offset 4): la última fila.
    let p3 = rt
        .execute_query_page("inventory.products.list", &params(json!({"limit": 2, "offset": 4})), &ctx())
        .await
        .unwrap();
    assert_eq!(p3.total, 5);
    assert_eq!(p3.rows.len(), 1);
    assert_eq!(p3.rows[0]["name"], json!("E"));
}

#[tokio::test]
async fn sort_by_whitelisted_column_desc() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let data = [("A", 1.0), ("B", 9.0), ("C", 5.0)];
    let rt = fresh_with_products(&data).await;
    let p = rt
        .execute_query_page("inventory.products.list", &params(json!({"sort": "price", "dir": "desc"})), &ctx())
        .await
        .unwrap();
    let names: Vec<&str> = p.rows.iter().map(|r| r["name"].as_str().unwrap()).collect();
    assert_eq!(names, ["B", "C", "A"], "orden por price desc");
}

#[tokio::test]
async fn invalid_sort_falls_back_to_default_no_error() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let data = [("Z", 1.0), ("A", 2.0)];
    let rt = fresh_with_products(&data).await;
    // Columna fuera de la whitelist (intento de inyección/typo) → cae a default_sort (name asc).
    let p = rt
        .execute_query_page(
            "inventory.products.list",
            &params(json!({"sort": "price; DROP TABLE inventory_product"})),
            &ctx(),
        )
        .await
        .unwrap();
    let names: Vec<&str> = p.rows.iter().map(|r| r["name"].as_str().unwrap()).collect();
    assert_eq!(names, ["A", "Z"], "sort no permitido → default name asc");
}

#[tokio::test]
async fn global_search_filters_rows() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let data = [("Café molido", 1.0), ("Té verde", 2.0), ("Café soluble", 3.0)];
    let rt = fresh_with_products(&data).await;
    let p = rt
        .execute_query_page("inventory.products.list", &params(json!({"search": "Café"})), &ctx())
        .await
        .unwrap();
    assert_eq!(p.total, 2);
    assert_eq!(p.rows.len(), 2);
}

#[tokio::test]
async fn range_filter_on_price() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let data = [("A", 1.0), ("B", 5.0), ("C", 9.0)];
    let rt = fresh_with_products(&data).await;
    let p = rt
        .execute_query_page(
            "inventory.products.list",
            &params(json!({"f_price_from": 2.0, "f_price_to": 8.0})),
            &ctx(),
        )
        .await
        .unwrap();
    assert_eq!(p.total, 1);
    assert_eq!(p.rows[0]["name"], json!("B"));
}

#[tokio::test]
async fn eq_filter_on_is_active() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let data = [("A", 1.0), ("B", 2.0)];
    let rt = fresh_with_products(&data).await;
    // Desactiva B.
    let id_b = {
        let all = rt
            .execute_query_page("inventory.products.list", &Params::new(), &ctx())
            .await
            .unwrap();
        all.rows.iter().find(|r| r["name"] == json!("B")).unwrap()["id"].as_str().unwrap().to_string()
    };
    rt.execute_command(
        "inventory.products.update",
        &params(json!({
            "product_id": id_b, "name": "B", "price": 2.0, "cost": 0,
            "low_stock_threshold": 5, "is_active": 0,
            // products.update es un REEMPLAZO completo (#178): lo no enviado se borraría en
            // silencio, así que el contrato exige ean13/description/tax_category_key explícitos.
            "ean13": null, "description": "", "tax_category_key": "product.generic"
        })),
        &ctx(),
    )
    .await
    .unwrap();

    // Sin filtro: ambos (la base ya NO hardcodea is_active=1).
    let all = rt
        .execute_query_page("inventory.products.list", &Params::new(), &ctx())
        .await
        .unwrap();
    assert_eq!(all.total, 2, "ahora se ven activos e inactivos");

    // f_is_active = 1 → solo A.
    let active = rt
        .execute_query_page("inventory.products.list", &params(json!({"f_is_active": 1})), &ctx())
        .await
        .unwrap();
    assert_eq!(active.total, 1);
    assert_eq!(active.rows[0]["name"], json!("A"));

    // f_is_active = 0 → solo B (responde a la duda original: el admin SÍ ve/gestiona inactivos).
    let inactive = rt
        .execute_query_page("inventory.products.list", &params(json!({"f_is_active": 0})), &ctx())
        .await
        .unwrap();
    assert_eq!(inactive.total, 1);
    assert_eq!(inactive.rows[0]["name"], json!("B"));
}

// ── el `limit` que pides es el `limit` que recibes ──────────────────────────────────────────
//
// Había un tope duro `MAX_LIMIT = 500` que hacía `limit.clamp(1, 500)`. Un hub con 800 productos
// pedía 800, recibía 500, y NADIE se enteraba: la respuesta no dice «te he truncado». Un tope que
// miente es peor que no tener tope — es el mismo fallo por el que un TPV solo vendía 50 platos.
//
// Contrato: el servidor devuelve lo que le pides. El que sabe cuántas filas necesita es quien
// llama (un TPV necesita TODOS sus productos; una tabla, una página).
#[tokio::test]
async fn un_hub_con_800_productos_los_ve_los_800() {
    if !erplora_runtime::require_modules_workspace() { return; }
    let productos: Vec<(String, f64)> = (0..800).map(|i| (format!("Producto {i:03}"), 1.0)).collect();
    let refs: Vec<(&str, f64)> = productos.iter().map(|(n, p)| (n.as_str(), *p)).collect();
    let rt = fresh_with_products(&refs).await;

    let page = rt
        .execute_query_page("inventory.products.list", &params(json!({"limit": 800})), &ctx())
        .await
        .expect("la query no falla");

    assert_eq!(page.total, 800, "el total anunciado son 800");
    assert_eq!(
        page.rows.len(),
        800,
        "pedí 800 filas y me tienen que llegar 800 — no 500 y a callar"
    );
    assert_eq!(page.limit, 800, "el `limit` que devuelve el sobre es el que pedí");
}
