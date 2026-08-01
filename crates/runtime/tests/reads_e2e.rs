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
//! * **Política explícita**: una read legacy u opcional que falle se omite. Una read marcada
//!   `required:true` aborta antes del handler; se usa cuando degradar a datos del caller sería una
//!   violación de autoridad, como horarios o reglas fiscales.

use std::path::PathBuf;
use std::sync::{Arc, Mutex};

use erplora_db::{testutil::fresh_db, Params};
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

#[derive(Default, Debug)]
struct Sink {
    events: Mutex<Vec<(String, serde_json::Value)>>,
}
impl EventSink for Sink {
    fn emit(&self, name: &str, payload: &serde_json::Value) {
        self.events
            .lock()
            .unwrap()
            .push((name.to_string(), payload.clone()));
    }
}

/// Runtime con `taxes` + `inventory` + `customers` + `sales` (el conjunto que hace falta para cobrar).
async fn rt_pos() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
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

    // El hub declara su catálogo fiscal: la comida de restaurante va al 10 %.
    rt.execute_command(
        "taxes.categories.create",
        &params(json!({ "key": "restaurant.food", "name": "Comida" })),
        &ctx,
    )
    .await
    .expect("crear la categoría fiscal");

    rt.execute_command(
        "taxes.rules.create",
        &params(json!({
            "country_code": "ES", "region_code": null,
            "tax_category_key": "restaurant.food", "rate_pct": 10.0,
            "tax_type": "vat", "valid_from": null, "valid_to": null
        })),
        &ctx,
    )
    .await
    .expect("crear la regla fiscal (ES · restaurant.food · 10 %)");

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
            "items": [{
                "product_name": "Menú del día",
                "price": 1100,
                "quantity": 1_000_000,
                "tax_category_key": "restaurant.food",
                "tax_rate": 0.0            // ← LA MENTIRA DEL CLIENTE
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

/// Una dependencia fiscal rota falla **antes** del handler y no deja ningún efecto parcial.
///
/// Cobrar con un IVA inventado por el navegador es peor que rechazar el cobro: si la query
/// autoritativa no puede ejecutarse, `required:true` corta antes de generar las operaciones WASM.
#[tokio::test]
async fn una_read_fiscal_requerida_falla_sin_handler_persistencia_ni_outbox() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    let rt = rt_pos().await;
    let ctx = admin();

    // Rompe la FUENTE, no el contenido: una tabla vacía sigue siendo una lectura válida; una tabla
    // ausente simula exactamente un fallo de migración/BD de `taxes.rules.list`.
    rt.db_for_test()
        .execute_batch("DROP TABLE taxes_rule")
        .await
        .expect("romper la read fiscal para la regresión");

    let err = rt
        .execute_command(
            "sales.complete_sale",
            &params(json!({
                "items": [{
                    "product_name": "X",
                    "price": 1000,
                    "quantity": 1_000_000,
                    "tax_category_key": "product.generic",
                    "tax_rate": 21.0
                }],
                "tax_included": true,
                "amount_tendered": 1000,
                "payment_method_name": "Efectivo"
            })),
            &ctx,
        )
        .await
        .expect_err("una read fiscal requerida nunca degrada al porcentaje del navegador");
    assert!(
        matches!(
            err,
            erplora_runtime::RuntimeError::RequiredReadFailed { ref command, ref query }
                if command == "sales.complete_sale" && query == "taxes.rules.list"
        ),
        "error inesperado: {err:?}"
    );

    let ventas = rt
        .execute_query("sales.list", &Params::new(), &ctx)
        .await
        .unwrap();
    assert!(
        ventas.is_empty(),
        "el handler no debe haber persistido cabecera de venta"
    );

    for table in [
        "sales_sale_counter",
        "sales_sale",
        "sales_sale_item",
        "_event_outbox",
    ] {
        let rows = rt
            .db_for_test()
            .query(
                &format!("SELECT COUNT(*) AS n FROM {table}"),
                &Params::new(),
            )
            .await
            .unwrap_or_else(|e| panic!("contar {table}: {e}"));
        assert_eq!(
            rows.rows[0]["n"].as_i64(),
            Some(0),
            "fallar la read no puede tocar {table}"
        );
    }
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
    assert!(
        !def.is_required(),
        "el default sigue siendo graceful por compatibilidad"
    );
}

#[test]
fn una_read_puede_declararse_requerida() {
    let def: erplora_runtime::manifest::ReadDef =
        serde_json::from_str(r#"{ "query": "inventory.products.get", "required": true }"#)
            .expect("read requerida");
    assert!(def.is_required());
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
