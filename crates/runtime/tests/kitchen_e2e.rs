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
use erplora_runtime::{EventSink, EventSource, RequestContext, Runtime};
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
    fn emit(&self, _source: EventSource<'_>, name: &str, payload: &serde_json::Value) {
        self.events.lock().unwrap().push((name.to_string(), payload.clone()));
    }
}

/// Runtime con inventory + sales + kitchen. **Sin `tables` ni `customers`**: si cocina necesitara
/// alguno de los dos para instalarse, seguiría sabiendo de ellos y este setup fallaría.
async fn fresh() -> (Runtime, Arc<Sink>) {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
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
    open_order_with(rt, ctx, json!([{ "product_name": product, "price": 350, "quantity": 2_000_000 }]))
        .await
}

/// Abre un pedido con las líneas EXACTAS que se le pidan.
///
/// Existe porque `sales.order.fire` dejó de fiarse de `payload.items` (kitchen#54): las líneas que
/// bajan a cocina salen de la read declarada sobre `sales_order_item`, o sea de filas reales. Un
/// test que quiera dos líneas, media ración o un `product_id` enrutado tiene que **sembrarlo aquí**;
/// mandarlo en el disparo ya no hace nada.
async fn open_order_with(rt: &Runtime, ctx: &RequestContext, items: serde_json::Value) -> String {
    let res = rt
        .execute_command("sales.order.open", &params(json!({ "items": items })), ctx)
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

    let oid = open_order_with(
        &rt,
        &ctx,
        json!([
            { "product_id": "prod-croquetas", "product_name": "Croquetas", "price": 350, "quantity": 2_000_000 },
            { "product_id": "prod-canas", "product_name": "Cañas", "price": 250, "quantity": 2_000_000 }
        ]),
    )
    .await;
    rt.execute_command(
        "sales.order.fire",
        &params(json!({ "order_id": oid, "label": "Mesa 4", "channel": "dine_in" })),
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
    let oid = open_order_with(
        &rt,
        &ctx,
        json!([{ "product_name": "Gambas", "price": 2400, "quantity": 500_000 }]),
    )
    .await;

    rt.execute_command(
        "sales.order.fire",
        &params(json!({ "order_id": oid, "label": "Mesa 4", "channel": "dine_in" })),
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

    let oid = open_order_with(
        &rt,
        &ctx,
        json!([{ "product_id": "prod-croquetas", "product_name": "Croquetas", "price": 350, "quantity": 2_000_000 }]),
    )
    .await;
    rt.execute_command(
        "sales.order.fire",
        &params(json!({ "order_id": oid, "label": "Mesa 4", "channel": "dine_in" })),
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

/// La versión de `kitchen` que trae la expansión del combo (ADR-0381). Los dos tests de abajo
/// aseguran cosas que NO existen por debajo de ella, y el checkout de módulos es compartido.
const COMBO_SINCE: &str = "2.3.27";

/// kitchen#57 · **cada componente del menú llega a SU estación, y siguen siendo un menú**
/// (ADR-0381).
///
/// El fallo estrella del sector no es de modelo, es de ENRUTADO, y está documentado en dos
/// productos maduros: en TouchBistro el componente hereda la impresora del PLATO PRINCIPAL —la
/// ensalada del menú sale por la parrilla— y en Square el combo imprime como un PÁRRAFO CORRIDO,
/// con un moderador confirmando que no hay forma de sacarlo como lista.
///
/// Este test entra por la puerta del listener (`kitchen.orders.create_from_order`) en vez de por
/// `sales.order.fire` **a propósito**: la expansión del combo en `sales` es `ERPlora/sales#152` y
/// aún no existe, pero el contrato de entrada de cocina sí, y lo que hay que probar aquí es que el
/// WASM compilado de verdad, el binder del runtime y `_insert_item.sql` se entienden — que es lo
/// que ni los tests del handler ni la batería de Postgres del módulo pueden decir por separado.
#[tokio::test]
async fn cada_componente_del_menu_llega_a_su_estacion_y_siguen_siendo_un_menu() {
    if !erplora_runtime::require_modules_workspace() { return; }
    // La expansión del combo llegó en kitchen 2.3.27. El checkout de módulos lo comparte la flota
    // y casi siempre va por detrás: sin este guard, este test pone en rojo el gate pre-push de
    // TODO el que empuje después, y no el de quien lo escribió.
    if !erplora_runtime::require_module_version("kitchen", COMBO_SINCE) { return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    let (rt, _) = fresh().await;
    let ctx = admin();

    // Tres estaciones de un restaurante de verdad: fríos, plancha y barra.
    let mut stations = Vec::new();
    for (name, product) in [("Fríos", "p-gazpacho"), ("Plancha", "p-entrecot"), ("Barra", "p-tinto")] {
        let st = rt
            .execute_command(
                "kitchen.stations.create",
                &params(json!({ "name": name, "destination": "both", "printer_role": "kitchen" })),
                &ctx,
            )
            .await
            .expect("crear la estación");
        let id = st["new_ids"][0].as_str().unwrap().to_string();
        rt.execute_command(
            "kitchen.stations.set_routing",
            &params(json!({ "station_id": id, "product_id": product })),
            &ctx,
        )
        .await
        .expect("enrutar el producto a su estación");
        stations.push((name.to_string(), id));
    }

    // El menú del día tal y como lo entrega ADR-0381 con `supply_kind = 'service'`: UNA línea de
    // venta a precio cerrado, con sus componentes en el snapshot.
    rt.execute_command(
        "kitchen.orders.create_from_order",
        &params(json!({
            "order_id": "ord-menu-1",
            "label": "Mesa 7",
            "channel": "dine_in",
            "items": [{
                "order_item_id": "li-1",
                "product_id": "combo-menu",
                "product_name": "Menú del día",
                "quantity": 1_000_000,
                "unit_price": 1350,
                "combo_group_ref": "cg-1",
                "combo_name": "Menú del día",
                "combo_kitchen_name": "MENÚ",
                "combo_components": [
                    { "product_id": "p-gazpacho", "product_name": "Gazpacho", "kitchen_name": "GAZPACHO", "quantity": 1_000_000 },
                    { "product_id": "p-entrecot", "product_name": "Entrecot", "kitchen_name": "ENTRECOT", "quantity": 1_000_000,
                      "modifiers": [{ "option_id": "o1", "name": "Sin cebolla", "kitchen_name": "SIN CEBOLLA" }] },
                    { "product_id": "p-tinto", "product_name": "Vino tinto", "quantity": 1_000_000 }
                ]
            }]
        })),
        &ctx,
    )
    .await
    .expect("materializar la comanda del menú");

    let comandas = rt.execute_query("kitchen.orders.list", &Params::new(), &ctx).await.unwrap();
    assert_eq!(comandas.len(), 1, "un menú es UNA comanda: {comandas:?}");
    let comanda_id = comandas[0]["id"].as_str().unwrap().to_string();
    // El precio cerrado se cuenta UNA vez: ni una línea padre a 0 € (el fallo de Odoo) ni el
    // precio repetido en cada componente, que sería el mismo embuste con el signo cambiado.
    assert_eq!(comandas[0]["total"], json!(1350), "el precio cerrado, una sola vez");

    let lineas = rt
        .execute_query("kitchen.orders.items", &params(json!({ "order_id": comanda_id })), &ctx)
        .await
        .unwrap();
    assert_eq!(lineas.len(), 3, "tres componentes, TRES líneas de comanda: {lineas:?}");

    // 🔴 Tres estaciones DISTINTAS, cada una la del artículo de su componente.
    let destinos: Vec<&str> =
        lineas.iter().map(|l| l["station_name"].as_str().unwrap_or("")).collect();
    assert_eq!(
        destinos,
        vec!["Fríos", "Plancha", "Barra"],
        "cada componente llega a la estación de SU artículo, nunca a la del plato de al lado \
         (el fallo de TouchBistro: la ensalada acaba en la parrilla)"
    );

    // …y siguen siendo un menú: mismo grupo, mismo nombre congelado, en el orden de elección.
    for l in &lineas {
        assert_eq!(l["combo_ref"], json!("cg-1"), "el grupo se pierde: {l:?}");
        assert_eq!(l["combo_name"], json!("MENÚ"), "manda el nombre de cocina: {l:?}");
    }
    let nombres: Vec<&str> = lineas.iter().map(|l| l["product_name"].as_str().unwrap_or("")).collect();
    assert_eq!(nombres, vec!["GAZPACHO", "ENTRECOT", "Vino tinto"]);
    let orden: Vec<i64> = lineas.iter().map(|l| l["line_seq"].as_i64().unwrap_or(0)).collect();
    assert_eq!(orden, vec![1, 2, 3], "el orden de ELECCIÓN, no el que devuelva el planificador");

    // El suplemento cuelga de SU componente: «el segundo, sin cebolla» no le quita la cebolla al
    // gazpacho.
    assert_eq!(lineas[1]["modifiers"], json!("SIN CEBOLLA"));
    assert_eq!(lineas[0]["modifiers"], json!(""));
    assert_eq!(lineas[2]["modifiers"], json!(""));

    // Y el feed del KDS lo ve: sin esto el WC no puede pintar cabecera + lista.
    let feed = rt.execute_query("kitchen.orders.display", &Params::new(), &ctx).await.unwrap();
    let del_menu: Vec<_> = feed.iter().filter(|r| r["combo_ref"] == json!("cg-1")).collect();
    assert_eq!(del_menu.len(), 3, "el KDS no puede agrupar lo que la query no proyecta: {feed:?}");
}

/// Un menú disparado SIN nada elegido no abre comanda: rechazo de dominio, ruidoso y sin escribir.
///
/// La puerta autoritativa del `min_choices` es de `sales` —es quien lee `combos.*`—, pero cocina no
/// puede depender de que TODO el que emita `order.fired` venga bien (un flujo, el asistente, una
/// integración de terceros). Mismo razonamiento y misma puerta que kitchen#54.
#[tokio::test]
async fn un_menu_sin_nada_elegido_no_abre_comanda() {
    if !erplora_runtime::require_modules_workspace() { return; }
    if !erplora_runtime::require_module_version("kitchen", COMBO_SINCE) { return; }
    if !wasm_present() {
        eprintln!("SKIP: falta handler.wasm");
        return;
    }
    let (rt, _) = fresh().await;
    let ctx = admin();

    let res = rt
        .execute_command(
            "kitchen.orders.create_from_order",
            &params(json!({
                "order_id": "ord-menu-2",
                "label": "Mesa 3",
                "channel": "dine_in",
                "items": [{
                    "order_item_id": "li-1", "product_id": "combo-menu", "product_name": "Menú del día",
                    "quantity": 1_000_000, "unit_price": 1350,
                    "combo_group_ref": "cg-2", "combo_name": "Menú del día",
                    "combo_components": []
                }]
            })),
            &ctx,
        )
        .await;

    let err = res.expect_err("un menú vacío tiene que rechazarse, no crear una tarjeta en blanco");
    let texto = format!("{err:?}");
    assert!(
        texto.contains("kitchen.combo_without_components"),
        "el rechazo tiene que decir POR QUÉ, con su código: {texto}"
    );

    let comandas = rt.execute_query("kitchen.orders.list", &Params::new(), &ctx).await.unwrap();
    assert!(comandas.is_empty(), "no se escribe nada: {comandas:?}");
}
