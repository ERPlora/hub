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

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{EventSink, RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(name: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(name)
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
    let db = fresh_db().await;
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
            &params(json!({ "items": [{ "product_name": product, "price": 350, "quantity": 2_000_000 }] })),
            ctx,
        )
        .await
        .unwrap();
    res["new_ids"][0].as_str().unwrap().to_string()
}

#[tokio::test]
async fn la_comanda_nace_del_pedido_y_no_hace_falta_ninguna_venta() {
    if !erplora_runtime::require_modules_workspace() { return; }
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
    if !erplora_runtime::require_modules_workspace() { return; }
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
    if !erplora_runtime::require_modules_workspace() { return; }
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
async fn cada_estacion_dice_a_donde_sale_su_comanda() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // Hasta ahora disparar guardaba la comanda en la BD **y ya**: nadie la imprimía y nadie
    // garantizaba que apareciese en una pantalla. Un restaurante real tiene varias estaciones y
    // cada una sale por donde puede: en la plancha nadie mira una pantalla con las manos ocupadas
    // (papel), y en la barra imprimir es tirar papel porque el camarero se sirve solo (pantalla).
    //
    // El destino es de la ESTACIÓN, no de la comanda: así "caliente imprime, barra solo pantalla"
    // se configura una vez y no en cada disparo. El enrutado producto→estación YA existía
    // (`_insert_item.sql`); lo que faltaba era que la estación dijera **a dónde**.
    let (rt, _) = fresh().await;
    let ctx = admin();

    let cocina = rt
        .execute_command(
            "kitchen.stations.create",
            &params(json!({ "name": "Cocina caliente", "destination": "printer", "printer_role": "kitchen" })),
            &ctx,
        )
        .await
        .expect("crear la estación de cocina");
    let cocina_id = cocina["new_ids"][0].as_str().unwrap().to_string();

    let barra = rt
        .execute_command(
            "kitchen.stations.create",
            &params(json!({ "name": "Barra", "destination": "display" })),
            &ctx,
        )
        .await
        .expect("crear la estación de barra");
    let barra_id = barra["new_ids"][0].as_str().unwrap().to_string();

    for (station_id, product_id) in [(&cocina_id, "prod-croquetas"), (&barra_id, "prod-canas")] {
        rt.execute_command(
            "kitchen.stations.set_routing",
            &params(json!({ "station_id": station_id, "product_id": product_id })),
            &ctx,
        )
        .await
        .expect("enrutar el producto a su estación");
    }

    let oid = open_order(&rt, &ctx, "Croquetas").await;
    rt.execute_command(
        "sales.order.fire",
        &params(json!({
            "order_id": oid, "label": "Mesa 4", "channel": "dine_in",
            "items": [
                { "product_id": "prod-croquetas", "product_name": "Croquetas", "quantity": 2_000_000, "unit_price": 350 },
                { "product_id": "prod-canas", "product_name": "Cañas", "quantity": 2_000_000, "unit_price": 250 }
            ]
        })),
        &ctx,
    )
    .await
    .expect("disparar el pedido a cocina");
    rt.drain_outbox().await.unwrap();

    let comandas = rt.execute_query("kitchen.orders.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(comandas.len(), 1, "un disparo, una comanda: {comandas:?}");
    let comanda_id = comandas[0]["id"].as_str().unwrap();

    let items = rt
        .execute_query("kitchen.orders.items", &params(json!({ "order_id": comanda_id })), &ctx)
        .await
        .unwrap();
    assert_eq!(items.len(), 2, "las dos líneas bajan a cocina: {items:?}");

    // La línea no solo sabe QUÉ estación: sabe por dónde sale esa estación. Es lo que necesita
    // quien imprime para agrupar por papel y no mandar a la impresora lo que es solo de pantalla.
    let croquetas =
        items.iter().find(|i| i["product_name"] == json!("Croquetas")).expect("línea de croquetas");
    assert_eq!(croquetas["station_id"], json!(cocina_id), "las croquetas van a la plancha");
    assert_eq!(croquetas["destination"], json!("printer"), "la cocina caliente imprime");
    assert_eq!(croquetas["printer_role"], json!("kitchen"), "y sale por el rol `kitchen`");

    let canas = items.iter().find(|i| i["product_name"] == json!("Cañas")).expect("línea de cañas");
    assert_eq!(canas["station_id"], json!(barra_id), "las cañas van a la barra");
    assert_eq!(canas["destination"], json!("display"), "la barra NO imprime: solo pantalla");
}

#[tokio::test]
async fn media_racion_llega_a_cocina_como_media_racion() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // `sales_order_item.quantity` es REAL —"cantidad fraccionable"— porque medio kilo de gambas o
    // media ración son cantidades reales de un bar. Pero cocina la guardaba en un INTEGER y el
    // handler la convertía con `as_i64`, que para 0.5 hace `0.5 as i64` = 0: al cocinero le
    // llegaba «0 × Gambas». En Postgres la columna INTEGER lo rompe del todo.
    //
    // Y esto es prerequisito del envío incremental: el delta es `quantity - dispatched`, así que
    // si cocina trunca, `sales` cree que comunicó 0.5 y cocina recibió 0 — la línea se reenviaría
    // en cada disparo, para siempre.
    let (rt, _) = fresh().await;
    let ctx = admin();
    let oid = open_order(&rt, &ctx, "Gambas").await;

    rt.execute_command(
        "sales.order.fire",
        &params(json!({
            "order_id": oid, "label": "Mesa 4", "channel": "dine_in",
            "items": [{ "product_name": "Gambas", "quantity": 500_000, "unit_price": 2400 }]
        })),
        &ctx,
    )
    .await
    .expect("disparar media ración");
    rt.drain_outbox().await.unwrap();

    let comandas = rt.execute_query("kitchen.orders.list", &Params::new(), &ctx).await.unwrap();
    let comanda_id = comandas[0]["id"].as_str().unwrap();
    let items = rt
        .execute_query("kitchen.orders.items", &params(json!({ "order_id": comanda_id })), &ctx)
        .await
        .unwrap();

    assert_eq!(items.len(), 1, "la línea baja a cocina: {items:?}");
    // ADR-0147 §2.1: la FILA también habla µ (kitchen 005): media ración se persiste como
    // 500000, nunca 0.5 en f64 (aquello era el residuo transitorio) ni 0 ni 1. El lógico
    // solo existe al pintar (print-comanda divide).
    assert_eq!(
        items[0]["quantity"].as_i64(),
        Some(500_000),
        "media ración es 500000 µ, ni 0 ni 1000000: {:?}",
        items[0]["quantity"]
    );
}

#[tokio::test]
async fn una_ronda_vieja_se_reimprime_por_donde_salio_de_verdad() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // El destino de una comanda YA DISPARADA es un hecho histórico, no una consulta a la
    // configuración de hoy. Si mañana mueven las croquetas de la plancha a la freidora, la ronda
    // que salió ayer SALIÓ por la plancha — y al reimprimirla tiene que volver a salir por ahí.
    //
    // Lo mismo vale para la anulación: el vale de «quita las croquetas» tiene que llegar a la
    // estación que las está cocinando, no a la que las cocinaría si se pidieran ahora.
    let (rt, _) = fresh().await;
    let ctx = admin();

    let plancha = rt
        .execute_command(
            "kitchen.stations.create",
            &params(json!({ "name": "Plancha", "destination": "printer", "printer_role": "kitchen" })),
            &ctx,
        )
        .await
        .unwrap();
    let plancha_id = plancha["new_ids"][0].as_str().unwrap().to_string();

    rt.execute_command(
        "kitchen.stations.set_routing",
        &params(json!({ "station_id": plancha_id, "product_id": "prod-croquetas" })),
        &ctx,
    )
    .await
    .unwrap();

    let oid = open_order(&rt, &ctx, "Croquetas").await;
    rt.execute_command(
        "sales.order.fire",
        &params(json!({
            "order_id": oid, "label": "Mesa 4", "channel": "dine_in",
            "items": [{ "product_id": "prod-croquetas", "product_name": "Croquetas", "quantity": 2_000_000, "unit_price": 350 }]
        })),
        &ctx,
    )
    .await
    .unwrap();
    rt.drain_outbox().await.unwrap();

    // El jefe reconfigura la estación DESPUÉS de que la ronda saliera: la plancha pasa a ser
    // solo-pantalla y cambia de rol de impresora. (Cambiar el ENRUTADO no basta para destapar
    // esto: `station_id` ya se congela al insertar la línea. Lo que sale del JOIN vivo, y por
    // tanto viaja en el tiempo, es la configuración de la estación.)
    rt.execute_command(
        "kitchen.stations.update",
        &params(json!({
            "station_id": plancha_id, "name": "Plancha (retirada)",
            "destination": "display", "printer_role": "bar"
        })),
        &ctx,
    )
    .await
    .unwrap();

    let comandas = rt.execute_query("kitchen.orders.list", &Params::new(), &ctx).await.unwrap();
    let comanda_id = comandas[0]["id"].as_str().unwrap();
    let items = rt
        .execute_query("kitchen.orders.items", &params(json!({ "order_id": comanda_id })), &ctx)
        .await
        .unwrap();

    assert_eq!(items[0]["station_id"], json!(plancha_id), "la ronda salió por la plancha");
    assert_eq!(
        items[0]["destination"],
        json!("printer"),
        "y por PAPEL, como salió — no por la pantalla de la freidora de hoy: {:?}",
        items[0]
    );
    assert_eq!(items[0]["printer_role"], json!("kitchen"), "por la impresora que la recibió");
    assert_eq!(items[0]["station_name"], json!("Plancha"), "con el nombre que tenía entonces");
}

#[tokio::test]
async fn la_cabecera_de_la_comanda_trae_lo_que_hay_que_imprimir() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // Quien imprime lee la cabecera con `kitchen.orders.get`. Si esa query no proyecta la
    // ETIQUETA, el papel sale con el destino vacío: comida en el pase sin saber a qué mesa va.
    // Es el mismo fallo que ya nos mordió con las rondas sin etiqueta, un eslabón más abajo — y un
    // test con la query mockeada no lo ve, porque el mock siempre devuelve la etiqueta.
    let (rt, _) = fresh().await;
    let ctx = admin();
    let oid = open_order(&rt, &ctx, "Croquetas").await;
    rt.execute_command(
        "sales.order.fire",
        &params(json!({
            "order_id": oid, "label": "Mesa 4", "channel": "dine_in",
            "items": [{ "product_name": "Croquetas", "quantity": 2_000_000, "unit_price": 350 }]
        })),
        &ctx,
    )
    .await
    .unwrap();
    rt.drain_outbox().await.unwrap();

    let comandas = rt.execute_query("kitchen.orders.list", &Params::new(), &ctx).await.unwrap();
    let comanda_id = comandas[0]["id"].as_str().unwrap();
    let cabecera = rt
        .execute_query("kitchen.orders.get", &params(json!({ "order_id": comanda_id })), &ctx)
        .await
        .unwrap();

    assert_eq!(cabecera.len(), 1, "la comanda existe: {cabecera:?}");
    assert_eq!(cabecera[0]["label"], json!("Mesa 4"), "sin etiqueta, el papel sale huérfano");
    assert_eq!(cabecera[0]["round_number"], json!(1), "la ronda va en el papel: ¿es la 1ª o la 3ª?");
    assert!(
        cabecera[0]["order_number"].as_str().is_some_and(|n| !n.is_empty()),
        "la comanda se identifica por número: {:?}",
        cabecera[0]["order_number"]
    );
}

#[tokio::test]
async fn una_estacion_sin_destino_configurado_imprime_y_se_muestra() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    // El default no puede ser "solo pantalla": un hub que actualiza y tenía sus estaciones de
    // siempre dejaría de imprimir sin que nadie toque nada, y la cocina se entera con la comida
    // fría. Ante la duda, las dos vías: sobra papel, pero no se pierde ninguna comanda.
    let (rt, _) = fresh().await;
    let ctx = admin();
    rt.execute_command("kitchen.stations.create", &params(json!({ "name": "Pase" })), &ctx)
        .await
        .expect("crear una estación sin decir su destino");

    let estaciones = rt.execute_query("kitchen.stations.list", &Params::new(), &ctx).await.unwrap();
    let pase = estaciones.iter().find(|s| s["name"] == json!("Pase")).expect("la estación Pase");
    assert_eq!(pase["destination"], json!("both"), "sin configurar, pantalla Y papel");
    assert_eq!(pase["printer_role"], json!("kitchen"), "y por la impresora de cocina");
}

#[tokio::test]
async fn una_ronda_sin_etiqueta_hereda_la_del_pedido() {
    if !erplora_runtime::require_modules_workspace() { return; }
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
