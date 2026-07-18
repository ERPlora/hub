//! ADR-0141 — la comanda de cocina nace del **PEDIDO**, no de la venta.
//!
//! Antes `kitchen` escuchaba `sale.completed`: en un restaurante eso manda la comida a la cocina
//! **al cobrar**, que es justo el final del servicio. La comanda tiene que salir cuando el camarero
//! **pide**, y el pedido puede seguir abierto una hora antes de que exista ninguna venta.
//!
//! El contrato que fijan estos tests: `sales` emite `order.fired` con `order_id`, una **etiqueta
//! opaca** (un texto que cocina imprime tal cual: "Mesa 4", "Barra", "Recogida Ana") y un **canal**
//! (`dine_in|takeaway|delivery`). Cocina NO sabe qué es una mesa ni un cliente — por eso la
//! etiqueta es opaca y `kitchen` no depende de `tables` ni de `customers`.

use std::path::PathBuf;
use std::sync::Arc;
use std::sync::Mutex;

use erplora_db::{Params, SqliteAdapter};
use erplora_runtime::{EventSink, RequestContext, Runtime};
use serde_json::json;

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
    mdir("kitchen").join("dist/handler.wasm").exists() && mdir("sales").join("dist/handler.wasm").exists()
}

#[derive(Default, Debug)]
struct Sink {
    events: Mutex<Vec<(String, serde_json::Value)>>,
}
impl EventSink for Sink {
    fn emit(&self, name: &str, payload: &serde_json::Value) {
        self.events.lock().unwrap().push((name.to_string(), payload.clone()));
    }
}

/// Runtime con inventory + sales + kitchen. **Sin `tables` ni `customers`**: si cocina necesitara
/// alguno de los dos para instalarse, seguiría sabiendo de ellos y este setup fallaría.
async fn fresh() -> (Runtime, Arc<Sink>) {
    let db = SqliteAdapter::open_in_memory().await.unwrap();
    let mut rt = Runtime::new(Box::new(db));
    let sink = Arc::new(Sink::default());
    rt.set_event_sink(sink.clone());
    rt.install_from_dir(&mdir("taxes")).await.expect("instalar taxes");
    rt.install_from_dir(&mdir("inventory")).await.expect("instalar inventory");
    rt.install_from_dir(&mdir("sales")).await.expect("instalar sales");
    rt.install_from_dir(&mdir("kitchen")).await.expect("instalar kitchen");
    (rt, sink)
}

/// Abre un pedido con una línea y devuelve su id.
async fn open_order(rt: &Runtime, ctx: &RequestContext, product: &str) -> String {
    let res = rt
        .execute_command(
            "sales.order.open",
            &params(json!({ "items": [{ "product_name": product, "price": 350, "quantity": 2 }] })),
            ctx,
        )
        .await
        .unwrap();
    res["new_ids"][0].as_str().unwrap().to_string()
}

#[tokio::test]
async fn la_comanda_nace_del_pedido_y_no_hace_falta_ninguna_venta() {
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    let (rt, _) = fresh().await;
    let ctx = admin();
    let oid = open_order(&rt, &ctx, "Croquetas").await;

    rt.execute_command(
        "sales.order.fire",
        &params(json!({ "order_id": oid, "label": "Mesa 4", "channel": "dine_in" })),
        &ctx,
    )
    .await
    .expect("disparar el pedido a cocina");
    rt.drain_outbox().await.unwrap();

    let comandas = rt.execute_query("kitchen.orders.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(comandas.len(), 1, "el pedido disparado crea UNA comanda: {comandas:?}");
    assert_eq!(comandas[0]["source_order_id"], json!(oid), "la comanda cuelga del pedido");
    assert_eq!(comandas[0]["label"], json!("Mesa 4"), "la etiqueta viaja opaca y se imprime tal cual");
    assert_eq!(comandas[0]["order_type"], json!("dine_in"));

    // Y todo esto SIN venta: la comida sale a cocina mucho antes de cobrar.
    let ventas = rt.execute_query("sales.list", &Params::new(), &ctx).await.unwrap();
    assert!(ventas.is_empty(), "no debe existir venta al disparar la comanda: {ventas:?}");
}

#[tokio::test]
async fn cada_disparo_del_mismo_pedido_es_una_ronda() {
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    let (rt, _) = fresh().await;
    let ctx = admin();
    let oid = open_order(&rt, &ctx, "Cañas").await;

    // Primero las bebidas, veinte minutos después la comida: dos comandas del MISMO pedido.
    for _ in 0..2 {
        rt.execute_command(
            "sales.order.fire",
            &params(json!({ "order_id": oid, "label": "Mesa 4", "channel": "dine_in" })),
            &ctx,
        )
        .await
        .unwrap();
        rt.drain_outbox().await.unwrap();
    }

    let comandas = rt.execute_query("kitchen.orders.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(comandas.len(), 2, "cada disparo es una ronda, no un duplicado: {comandas:?}");
    let mut rondas: Vec<i64> =
        comandas.iter().map(|c| c["round_number"].as_i64().unwrap_or(0)).collect();
    rondas.sort_unstable();
    assert_eq!(rondas, vec![1, 2], "las rondas se numeran por pedido");
}

#[tokio::test]
async fn cocina_no_conoce_mesas_ni_clientes() {
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // El manifest de kitchen no puede depender de `tables` ni de `customers`: la comanda se
    // identifica con la etiqueta opaca que le manda quien dispara, no con una FK a la mesa.
    let manifest =
        std::fs::read_to_string(mdir("kitchen").join("module.json")).expect("module.json de kitchen");
    let m: serde_json::Value = serde_json::from_str(&manifest).unwrap();
    let deps: Vec<&str> =
        m["depends_on"].as_array().unwrap().iter().map(|d| d.as_str().unwrap()).collect();
    assert!(!deps.contains(&"tables"), "cocina no depende de tables: {deps:?}");
    assert!(!deps.contains(&"customers"), "cocina no depende de customers: {deps:?}");

    // Y ya no escucha `sale.completed`: la comanda no la dispara el cobro.
    let listen = &m["events"]["listen"];
    assert!(listen.get("sale.completed").is_none(), "cocina no debe colgar del cobro: {listen}");
    assert!(listen.get("order.fired").is_some(), "cocina cuelga del disparo del pedido: {listen}");
}

#[tokio::test]
async fn una_ronda_sin_etiqueta_hereda_la_del_pedido() {
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // Encontrado en el navegador: el camarero manda las bebidas de la Mesa 4, y al reanudar el
    // pedido más tarde (otro turno, otra tablet, el POS sin la mesa cargada) la segunda comanda
    // salía con el destino VACÍO. En cocina eso es un ticket huérfano: comida sin saber a dónde va.
    // La etiqueta es del PEDIDO, aunque la aporte quien dispara: si un disparo no la trae, hereda.
    let (rt, _) = fresh().await;
    let ctx = admin();
    let oid = open_order(&rt, &ctx, "Cañas").await;

    for label in ["Mesa 4", ""] {
        rt.execute_command(
            "sales.order.fire",
            &params(json!({ "order_id": oid, "label": label, "channel": "dine_in" })),
            &ctx,
        )
        .await
        .unwrap();
        rt.drain_outbox().await.unwrap();
    }

    let comandas = rt.execute_query("kitchen.orders.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(comandas.len(), 2);
    for c in &comandas {
        assert_eq!(c["label"], json!("Mesa 4"), "toda ronda del pedido va a la misma mesa: {c:?}");
    }
}
