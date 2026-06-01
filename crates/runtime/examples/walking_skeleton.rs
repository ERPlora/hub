//! Walking skeleton de la Fase 1 (ARQUITECTURA.md §12): instala el módulo `inventory`,
//! aplica su migración SQLite, y ejecuta command → query → evento end-to-end.
//!
//! Ejecutar (cuando haya toolchain de Rust):
//!   cargo run -p erplora-runtime --example walking_skeleton
use std::path::PathBuf;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    // BD SQLite en memoria (en local sería app_data/erplora.db).
    let db = SqliteAdapter::open_in_memory()?;
    let mut rt = Runtime::new(Box::new(db));

    // Instala el módulo de ejemplo desde su carpeta.
    let module_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../modules/inventory");
    let id = rt.install_from_dir(&module_dir)?;
    println!("✓ instalado módulo: {id}");
    println!("  menú: {:?}", rt.navigation().iter().map(|n| &n.nav.label).collect::<Vec<_>>());

    // Contexto: hub h1, usuario u1, con permisos de admin (comodín).
    let ctx = RequestContext::new("h1", "u1", ["*".to_string()]);

    // 1) Alta de producto (command, en transacción, emite inventory.products.created).
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Café molido 250g", "sku": "CAF-250", "price": 4.5, "stock": 20 })),
        &ctx,
    )?;
    rt.execute_command(
        "inventory.products.create",
        &params(json!({ "name": "Leche entera 1L", "sku": "LEC-1L", "price": 1.2, "stock": 50 })),
        &ctx,
    )?;
    println!("✓ 2 productos creados");

    // 2) Listado (query, scope hub_id automático).
    let rows = rt.execute_query("inventory.products.list", &Params::new(), &ctx)?;
    println!("✓ inventory.products.list → {} filas:", rows.len());
    for r in &rows {
        println!("   - {} ({}) · {} € · stock {}", r["name"], r["sku"], r["price"], r["stock"]);
    }

    // 3) Evento entre módulos: simulamos pos.sale.completed → el listener descuenta stock.
    //    (En real lo emite el módulo POS al cobrar; aquí ejecutamos el command suscrito.)
    let cafe_id = rows
        .iter()
        .find(|r| r["sku"] == json!("CAF-250"))
        .and_then(|r| r["id"].as_str())
        .unwrap()
        .to_string();
    rt.execute_command(
        "inventory.stock.decrease",
        &params(json!({ "product_id": cafe_id, "qty": 3 })),
        &ctx,
    )?;
    let rows = rt.execute_query("inventory.products.list", &Params::new(), &ctx)?;
    let cafe = rows.iter().find(|r| r["sku"] == json!("CAF-250")).unwrap();
    println!("✓ stock de café tras descontar 3: {}", cafe["stock"]);

    println!("\n✓ Walking skeleton OK: manifest + migración + permisos + command + query + evento.");
    Ok(())
}
