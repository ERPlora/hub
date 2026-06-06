//! E2E del motor de listas (paginación + búsqueda + orden por whitelist + filtro por columna).
//! Usa el bloque `list` real de `inventory.products.list` sobre SQLite en memoria.
use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn inventory_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../modules/inventory")
}

fn ctx() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn fresh_with_products(names_prices: &[(&str, f64)]) -> Runtime {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&inventory_dir()).await.expect("instalar inventory");
    for (i, (name, price)) in names_prices.iter().enumerate() {
        rt.execute_command(
            "inventory.products.create",
            &params(json!({
                "name": name, "sku": format!("SKU-{i}"), "price": price, "cost": 0,
                "stock": (i as i64) + 1, "low_stock_threshold": 5, "product_type": "physical",
                "ean13": null, "description": "", "tax_class_id": null, "image": ""
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
            "low_stock_threshold": 5, "is_active": 0
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
