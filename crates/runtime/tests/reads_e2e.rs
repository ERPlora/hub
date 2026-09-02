//! **`reads`: el servidor le PRE-CARGA al handler las lecturas de confianza** (ADR-0069).
//!
//! # El agujero que cierra
//!
//! Hasta ahora, `sales.complete_sale` recibía el **`tax_rate` de cada línea DESDE EL CLIENTE** y se
//! fiaba. O sea: **el navegador decidía el IVA que se le declara a la AEAT**. Un cliente
//! manipulado (o simplemente con una caché vieja) podía mandar un 0 % donde tocaba un 21 %.
//!
//! ADR-0069 lo diseñó y se aceptó en junio, pero **nunca se implementó**: `sales` declaraba
//! `reads: ["taxes.rules.list"]` en su manifest y el runtime **ignoraba el campo en silencio**,
//! así que `context.reads` llegaba vacío y el handler caía a su fallback… que es la pista del
//! cliente. El diseño estaba bien; faltaba el host.
//!
//! # El mecanismo
//!
//! Un command declara `reads: ["<query>", …]`. El runtime **ejecuta esas queries ANTES** de invocar
//! el handler WASM y le inyecta las filas en `context.reads["<query>"]`. El handler ya no depende
//! de lo que le cuente el cliente: tiene el **catálogo de confianza** del hub.
//!
//! Reglas (ADR-0069 §1):
//! * **Alcance**: queries del propio módulo o de los que declara en `depends_on`. Un módulo no
//!   puede leer las tablas de un módulo con el que no tiene contrato.
//! * **Ejecución interna**: se corren con el contexto del SISTEMA, no con el permiso del usuario —
//!   el permiso del command ya se comprobó, y las reads son contrato *vouched* por el autor del
//!   módulo. Un empleado de POS sin `taxes.view_tax` igual obtiene los tipos, porque los necesita
//!   para cobrar.
//! * **Errores graceful**: una read que falle se **omite** (no revienta el command). El handler ya
//!   tiene fallback; lo que no puede es quedarse sin cobrar porque `taxes` esté raro.

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use erplora_db::{testutil::fresh_db, Params};
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

#[derive(Default, Debug)]
struct Sink {
    events: Mutex<Vec<(String, serde_json::Value)>>,
}
impl EventSink for Sink {
    fn emit(&self, _source: EventSource<'_>, name: &str, payload: &serde_json::Value) {
        self.events
            .lock()
            .unwrap()
            .push((name.to_string(), payload.clone()));
    }
}

/// Id of the CASH payment method from the hub's seeded catalog (hub#594): with runtime and ctx
/// sharing "h1" the `sales` seed is visible and `complete_sale` enforces `payment_method_id`.
async fn cash_method_id(rt: &Runtime, ctx: &RequestContext) -> String {
    let rows = rt
        .execute_query("sales.payment_methods", &Params::new(), ctx)
        .await
        .expect("sales.payment_methods");
    rows.iter()
        .find(|r| r["type"] == json!("cash"))
        .unwrap_or_else(|| panic!("the hub's catalog must carry the `cash` method: {rows:?}"))["id"]
        .as_str()
        .expect("payment method id")
        .to_string()
}

/// Runtime con `taxes` + `inventory` + `customers` + `sales` (el conjunto que hace falta para cobrar).
async fn rt_pos() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    rt.set_event_sink(Arc::new(Sink::default()));
    for m in ["taxes", "inventory", "customers", "sales"] {
        rt.install_from_dir(&mdir(m))
            .await
            .unwrap_or_else(|e| panic!("instalar {m}: {e}"));
    }
    rt
}

/// El caso que da nombre a todo esto: **el cliente MIENTE sobre el IVA y el servidor lo ignora**.
///
/// El hub tiene una regla fiscal que dice que `restaurant.food` va al 10 %. El POS manda la línea
/// con `tax_category_key: "restaurant.food"` y —maliciosamente o por bug— un `tax_rate: 0.0`.
///
/// El servidor debe declarar **el 10 % del catálogo**, no el 0 % del cliente.
#[tokio::test]
async fn el_servidor_resuelve_el_iva_del_catalogo_e_ignora_lo_que_diga_el_cliente() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = rt_pos().await;
    let ctx = admin();

    // The hub declares its fiscal catalog: this menu category is taxed at 10 %. A test-owned key
    // is used instead of the seeded `restaurant.food` (hub#594: with runtime and ctx sharing
    // "h1" the taxes seed IS visible, and re-creating a seeded category collides on
    // `(hub_id, key)`) — it also proves the resolution reads the catalog, not a seed default.
    rt.execute_command(
        "taxes.categories.create",
        &params(json!({ "key": "test.menu", "name": "Comida" })),
        &ctx,
    )
    .await
    .expect("crear la categoría fiscal");

    rt.execute_command(
        "taxes.rules.create",
        &params(json!({
            "country_code": "ES", "region_code": null,
            "tax_category_key": "test.menu", "rate_pct": 10.0,
            "tax_type": "vat", "valid_from": null, "valid_to": null
        })),
        &ctx,
    )
    .await
    .expect("crear la regla fiscal (ES · test.menu · 10 %)");

    // Guardarraíl del propio test: si la regla no llegó al catálogo, no estaría probando nada.
    let reglas = rt
        .execute_query("taxes.rules.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert!(
        !reglas.is_empty(),
        "la regla fiscal no se sembró: el test no probaría nada"
    );

    // El POS cobra un menú de 11,00 € (IVA incluido) diciendo que su IVA es 0 %.
    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            // `idempotency_key` of the charge attempt (sales#20, mandatory since v2.13.x).
            "idempotency_key": "reads-e2e-menu-del-dia",
            "payment_method_id": cash_method_id(&rt, &ctx).await,
            "items": [{
                "product_name": "Menú del día",
                "price": 1100,
                "quantity": 1_000_000,
                "tax_category_key": "test.menu",
                "tax_rate": 0.0            // ← THE CLIENT'S LIE
            }],
            "tax_included": true,
            "amount_tendered": 1100,
            "payment_method_name": "Efectivo"
        })),
        &ctx,
    )
    .await
    .expect("completar la venta");

    let ventas = rt
        .execute_query("sales.list", &Params::new(), &ctx)
        .await
        .unwrap();
    let v = &ventas[0];

    // Si el runtime NO pre-cargara las reads, el handler caería al fallback (la pista del cliente)
    // y declararía 0 € de IVA sobre una base de 11,00 €. Con el catálogo de confianza declara el
    // 10 %: base 10,00 € + cuota 1,00 €.
    assert_eq!(
        v["total"].as_i64().unwrap(),
        1100,
        "lo que paga el cliente no cambia"
    );
    assert_ne!(
        v["tax_amount"].as_i64().unwrap(),
        0,
        "el servidor se creyó el 0 % del cliente → el IVA lo sigue decidiendo el navegador"
    );
    assert_eq!(
        v["tax_amount"].as_i64().unwrap(),
        100,
        "10 % de una base de 10,00 € = 1,00 € — del CATÁLOGO del hub, no del cliente"
    );

    // Y el desglose que iría al XML de VeriFactu declara el 10 %, no el 0 % que mandó el POS.
    // (`sales.list` no trae el desglose; se lee de la fila.)
    let filas = rt
        .execute_query("sales.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert_eq!(filas.len(), 1);
}

/// Una `read` que no se puede resolver **no revienta el command**: el handler degrada.
///
/// Cobrar es lo último que puede fallar en un TPV. Si `taxes` está raro o la query no existe, la
/// venta se completa igual (con la pista del cliente como último recurso) — pero se completa.
#[tokio::test]
async fn una_read_que_falla_no_impide_cobrar() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    // The full stack is installed. Since hub#594 the seeded fiscal catalog IS visible (runtime
    // and ctx share "h1"), so the empty-catalog scenario is built per-line: the item carries NO
    // `tax_category_key`, so the trusted catalog cannot resolve it and the handler must degrade
    // to the client hint — and the sale must still complete, because charging is the last thing
    // allowed to fail in a POS.
    let rt = rt_pos().await;
    let ctx = admin();

    // Line without a fiscal category: the catalog has nothing to match it against.
    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "idempotency_key": "reads-e2e-sin-catalogo-fiscal",
            "payment_method_id": cash_method_id(&rt, &ctx).await,
            "items": [{ "product_name": "X", "price": 1000, "quantity": 1_000_000, "tax_rate": 21.0 }],
            "tax_included": true,
            "amount_tendered": 1000,
            "payment_method_name": "Efectivo"
        })),
        &ctx,
    )
    .await
    .expect("la venta DEBE completarse aunque no haya catálogo fiscal");

    let ventas = rt
        .execute_query("sales.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert_eq!(ventas.len(), 1, "el TPV cobró");
    assert_eq!(ventas[0]["total"].as_i64().unwrap(), 1000);
}

// ── `reads` CON PARÁMETROS (ADR-0069 fase 2) ────────────────────────────────────────────────────
//
// El límite que quedaba: las reads se ejecutaban con `Params::new()` — vacíos. Un handler podía
// pedir «todas las reglas de IVA» pero NO «la unidad de ESTE producto», así que cualquier
// validación que dependa de la fila concreta se quedaba sin sitio donde vivir:
//
//   * en el SQL no vale — un `WHERE` que no casa ninguna fila responde `ok`, no error;
//   * en el handler no valía — no podía leer la fila;
//   * pedírselo al cliente rompe que el servidor sea la autoridad.
//
// Es el mismo límite que ya había decidido tres diseños: por él las líneas de venta viajan en el
// payload, por él la comanda resuelve la estación en SQL, y por él ADR-0147 se quedaba sin poder
// rechazar una cantidad fuera de rejilla.
//
// Forma declarativa, retrocompatible: una read es un string (sin parámetros, como hasta ahora) o
// un objeto `{ query, params }` donde cada valor referencia un campo del payload del command.

#[test]
fn una_read_sin_parametros_sigue_siendo_un_string() {
    // Retrocompatibilidad: los manifests existentes declaran `reads: ["taxes.rules.list"]`.
    let def: erplora_runtime::manifest::ReadDef =
        serde_json::from_str(r#""taxes.rules.list""#).expect("string suelto");
    assert_eq!(def.query(), "taxes.rules.list");
    assert!(
        def.resolve_params_from_map(&Params::new()).is_empty(),
        "sin parámetros"
    );
}

#[test]
fn una_read_parametrizada_toma_el_valor_del_payload() {
    // La forma nueva: `{ query, params }`, con los valores referenciando el payload del command.
    let def: erplora_runtime::manifest::ReadDef = serde_json::from_str(
        r#"{ "query": "inventory.products.get", "params": { "product_id": "payload.product_id" } }"#,
    )
    .expect("forma con parámetros");
    assert_eq!(def.query(), "inventory.products.get");

    let payload = params(serde_json::json!({ "product_id": "prod-1", "qty": 500 }));
    let resueltos = def.resolve_params_from_map(&payload);
    assert_eq!(
        resueltos.get("product_id"),
        Some(&serde_json::json!("prod-1"))
    );
    assert_eq!(
        resueltos.len(),
        1,
        "solo lo declarado, no el payload entero"
    );
}

#[test]
fn un_campo_ausente_del_payload_resuelve_a_null_no_revienta() {
    // Regla 3 de ADR-0069: fallo graceful. Un parámetro que no está no puede abortar un cobro;
    // la query recibirá NULL y devolverá cero filas, y el handler degrada a su fallback.
    let def: erplora_runtime::manifest::ReadDef = serde_json::from_str(
        r#"{ "query": "inventory.products.get", "params": { "product_id": "payload.no_existe" } }"#,
    )
    .unwrap();
    let resueltos = def.resolve_params_from_map(&params(serde_json::json!({ "otro": 1 })));
    assert_eq!(resueltos.get("product_id"), Some(&serde_json::Value::Null));
}

// ── `required` (hub#701): la read OBLIGATORIA aborta en vez de degradar ─────────────────────────
//
// El defecto sigue siendo graceful (regla 3): una read que falla se omite. Pero la read de la que
// depende el IMPUESTO no puede admitir adivinar: si `taxes.rules.list` llega vacía, el handler no
// distingue «no hay reglas» de «el catálogo nunca llegó» y cae al `tax_rate` del payload — que es
// justo lo que sales#21 prohíbe. `required` hace que el runtime aborte con `ReadUnavailable`.

#[test]
fn una_read_string_nunca_es_required() {
    // La forma simple no puede ser obligatoria: el caso fácil sigue siendo el caso graceful.
    let def: erplora_runtime::manifest::ReadDef =
        serde_json::from_str(r#""taxes.rules.list""#).unwrap();
    assert!(!def.is_required());
}

#[test]
fn una_read_parametrizada_por_defecto_no_es_required() {
    // El flag es opt-in: si no se declara, la read sigue siendo graceful.
    let def: erplora_runtime::manifest::ReadDef =
        serde_json::from_str(r#"{ "query": "taxes.rules.list" }"#).unwrap();
    assert!(!def.is_required());
}

#[test]
fn una_read_parametrizada_puede_declararse_required() {
    let def: erplora_runtime::manifest::ReadDef =
        serde_json::from_str(r#"{ "query": "taxes.rules.list", "required": true }"#).unwrap();
    assert_eq!(def.query(), "taxes.rules.list");
    assert!(def.is_required());
}

/// Una read **normal** (sin `required`) que falla sigue siendo graceful: el command se ejecuta.
///
/// Este es el guardrail de no-regresión: el defecto no cambia. Solo la read marcada aborta.
#[test]
fn una_read_normal_que_falla_sigue_siendo_graceful() {
    // El defecto no cambia: la forma string y la forma objeto sin `required` ambas responden
    // `false` a `is_required()`, y eso es lo que `preload_reads` consulta para decidir si aborta
    // o si omite y deja al handler degradar.
    let def_str: erplora_runtime::manifest::ReadDef = serde_json::from_str(r#""x.y.z""#).unwrap();
    assert!(!def_str.is_required(), "la forma string nunca es required");

    let def_obj: erplora_runtime::manifest::ReadDef =
        serde_json::from_str(r#"{ "query": "x.y.z" }"#).unwrap();
    assert!(
        !def_obj.is_required(),
        "sin el flag, una read objeto no es required"
    );
}
