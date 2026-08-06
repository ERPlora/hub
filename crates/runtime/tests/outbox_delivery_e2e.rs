//! Regresión E2E de **hub#142** (P0): el Outbox no entregaba eventos en algunos hubs.
//!
//! Dos síntomas, ambos por el MISMO contrato roto del relay del outbox (`outbox.rs::process_row` /
//! `process_once`) — arreglado en este mismo cambio:
//!
//! 1. **Un listener que falla bloqueaba a sus hermanos.** `sale.voided` tenía dos listeners
//!    (`cash_register._reverse_sale`, `inventory._restock_on_void`); si el primero reventaba, el
//!    relay hacía `return` y el SEGUNDO nunca corría → el evento aparecía "sin llegar" a la mitad
//!    de los módulos. No determinista: dependía de qué listener fallaba y del orden del relay.
//! 2. **Un evento devuelto por un handler (`Output.events`) no llegaba a los listeners.** La cadena
//!    era `handler → persist_handler_output (encola en el outbox) → relay → listener`. El enqueue
//!    ya iba en la transacción del command (correcto); lo que fallaba era la ENTREGA del relay por
//!    la causa (1): cualquier otra fila venenosa en el mismo lote abortaba la entrega de esta.
//!
//! Estos tests reproducen ambos síntomas por el camino REAL (`Runtime::execute_command` →
//! `_event_outbox` → `Runtime::drain_outbox` → listener) con módulos instalados desde disco, como
//! los `*_e2e.rs`. Para el síntoma (2) se usa un handler **nativo** (ADR-0009): comparte el camino
//! EXACTO de `Output.events` con el WASM (`commands::persist_handler_output`) sin necesitar un
//! `.wasm` compilado — ver `wasm_tier2.rs` y los tests inline de `commands.rs`.
//!
//! Postgres real, schema efímero por test (`erplora_db::testutil::fresh_db`).
use std::path::PathBuf;
use std::sync::Arc;

use async_trait::async_trait;
use erplora_db::{testutil::fresh_db, Params};
use erplora_runtime::{native::NativeHandler, RequestContext, Runtime};
use erplora_wasm_host::{Event, Output};
use serde_json::json;

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests").join("fixture_outbox142").join(name)
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

/// Devuelve cuántas veces corrió el listener `name` (tabla `ob_log` del fixture). Lectura directa
/// por `db_for_test` (la aserción es de test, no de negocio: no hace falta una query declarada).
async fn runs(rt: &Runtime, name: &str) -> i64 {
    let mut p = Params::new();
    p.insert("name".into(), json!(name));
    let rows = rt
        .db_for_test()
        .query("SELECT runs FROM ob_log WHERE listener = :name", &p)
        .await
        .unwrap();
    rows.rows
        .first()
        .and_then(|r| r["runs"].as_i64())
        .unwrap_or(0)
}

/// Handler nativo del módulo `ob`: NO hace operaciones, solo devuelve un evento en
/// `Output.events`. Reproduce el síntoma (2): un evento que nace del handler (no del `emit`
/// declarativo) y debe llegar al listener `ob.handler_listener` por el relay.
#[derive(Debug)]
struct EmittingHandler;

#[async_trait]
impl NativeHandler for EmittingHandler {
    async fn call(
        &self,
        _function: &str,
        _input: &serde_json::Value,
        _host: &dyn erplora_runtime::native::NativeHost,
    ) -> Result<Output, erplora_runtime::errors::RuntimeError> {
        Ok(Output {
            operations: vec![],
            events: vec![Event {
                name: "ob.from_handler".to_string(),
                payload: json!({}),
            }],
            ..Output::default()
        })
    }
}

/// Runtime con `ob` + `ob2` instalados y el handler nativo de `ob` registrado. `ob2` es un módulo
/// distinto que ESCUCHA el mismo `ob.e` que el listener roto de `ob` — así probamos que un fallo
/// en el listener de UN módulo no bloquea la entrega al listener de OTRO módulo (caso real:
/// cash_register vs inventory sobre `sale.voided`).
async fn runtime() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&fixture("ob")).await.expect("instalar ob");
    rt.install_from_dir(&fixture("ob2")).await.expect("instalar ob2");
    rt.register_native("ob", Arc::new(EmittingHandler));
    rt
}

/// **hub#142 — síntoma (1): un listener que falla NO bloquea a su hermano.**
///
/// `ob.fire` emite `ob.e`; este evento tiene DOS listeners: `ob.bad` (SQL roto → falla siempre) y
/// `ob2.good` (SQL válido → incrementa `ob_log.good`). Antes del fix, el relay abortaba al primer
/// listener que fallaba (`return defer_or_dead`), así que `ob2.good` NUNCA corría: el hermano sano
/// moría de hambre por culpa del venenoso. Ahora cada listener es independiente.
#[tokio::test]
async fn a_failing_listener_does_not_block_its_sibling() {
    let rt = runtime().await;

    // Dispara el evento. `ob.bad` es el listener de `ob` en `ob.e`; `ob2.good` es el de `ob2`.
    rt.execute_command("ob.fire", &Params::new(), &admin()).await.unwrap();
    // Antes del drain, ningún listener ha corrido (entrega 100% asíncrona vía relay).
    assert_eq!(runs(&rt, "good").await, 0, "el listener no corre inline; va por el relay");

    // Un ciclo del relay: `ob.bad` falla, pero `ob2.good` SE ENTREGA igual.
    rt.drain_outbox().await.unwrap();
    assert_eq!(
        runs(&rt, "good").await,
        1,
        "el hermano bueno corre aunque el venenoso falle antes (hub#142)"
    );

    // La entrega del bueno quedó marcada (idempotente); la del malo, no.
    let delivered: Vec<String> = rt
        .db_for_test()
        .query(
            "SELECT listener_command FROM _event_delivery ORDER BY listener_command",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows
        .iter()
        .map(|r| r["listener_command"].as_str().unwrap().to_string())
        .collect();
    assert!(
        delivered.contains(&"ob2.good".to_string()),
        "el listener bueno quedó marcado como entregado: {delivered:?}"
    );
    assert!(
        !delivered.contains(&"ob.bad".to_string()),
        "el listener malo NO se marcó (falló) → se reintenta: {delivered:?}"
    );

    // Re-drenar no duplica al bueno (idempotencia por _event_delivery). El malo sigue fallando.
    rt.drain_outbox().await.unwrap();
    assert_eq!(runs(&rt, "good").await, 1, "reentrega no duplica el listener bueno (idempotente)");
}

/// **hub#142 — síntoma (2): un evento devuelto por un handler (`Output.events`) llega a los
/// listeners.**
///
/// `ob.emit_handler` es un command con handler **nativo** (mismo camino `Output.events` que el
/// WASM, vía `persist_handler_output`) que devuelve el evento `ob.from_handler`. Su listener
/// `ob.handler_listener` escribe en `ob_log.handler`. Antes del fix este evento se encolaba bien
/// (la escritura atómica del outbox ya funcionaba) pero NO se entregaba: cualquier fila venenosa
/// del lote abortaba el ciclo del relay → el KDS siempre vacío (kitchen.logs.list == 0). Ahora el
/// handler-emitted llega al listener por el relay.
/// **hub#142 — síntoma (2): un evento devuelto por un handler (`Output.events`) llega a los
/// listeners por el relay.**
///
/// El issue reporta que los `Output.events` de los handlers WASM (p.ej. kitchen) «nunca llegaban a
/// los listeners» (`kitchen.logs.list` siempre 0 → pestaña «Pantalla» del KDS vacía). La cadena es
/// `handler → commands::persist_handler_output (encola en el outbox en la MISMA tx del command) →
/// relay → listener`. El ENQUEUE ya era correcto; la entrega fallaba por el bug del relay (síntoma
/// 1): un listener que reventaba en OTRA fila del mismo lote abortaba la entrega de todas las
/// demás, y el síntoma era no determinista (dependía del estado/carrera del relay por hub).
///
/// Este test cubre el CAMINO COMPLETO del evento del handler de punta a punta, CON una fila
/// venenosa concurrente en el mismo lote para reproducir el escenario del issue: disparamos
/// PRIMERO `ob.fire` (cuyo listener `ob.bad` falla) y DESPUÉS `ob.emit_handler` (handler nativo
/// que devuelve `ob.from_handler` — mismo camino `Output.events` que el WASM). Un SOLO ciclo del
/// relay entrega el evento del handler y difiere el venenoso. (Cobertura positiva del camino del
/// handler-event; la REGRESIÓN dura del bloqueo entre listeners la cubre
/// `a_failing_listener_does_not_block_its_sibling`.)
#[tokio::test]
async fn a_handler_emitted_event_reaches_listeners_alongside_a_failing_sibling_row() {
    let rt = runtime().await;

    // (1) Una fila cuyo listener falla: `ob.fire` → `ob.e` → `ob.bad` (SQL roto). Cae PRIMERO
    //     en el orden del lote (created_at) — el escenario "fila venenosa" del issue.
    rt.execute_command("ob.fire", &Params::new(), &admin()).await.unwrap();
    // (2) Evento del HANDLER: `ob.emit_handler` devuelve `ob.from_handler` en `Output.events`.
    //     Se encola en el outbox dentro de la misma tx del command; cae DESPUÉS en el lote.
    rt.execute_command("ob.emit_handler", &Params::new(), &admin()).await.unwrap();
    assert_eq!(runs(&rt, "handler").await, 0, "el handler-emitted event no se entrega inline");

    // Un SOLO ciclo del relay procesa ambas filas (BATCH=50). La venenosa falla y se difiere;
    // la del handler se entrega igual.
    rt.process_outbox().await.unwrap();
    assert_eq!(
        runs(&rt, "handler").await,
        1,
        "un evento devuelto por Output.events llega a su listener en el mismo ciclo que una fila \
         que falla (hub#142)"
    );

    // La fila del handler quedó entregada; la venenosa, diferida (pendiente de reintento).
    let rows = rt
        .db_for_test()
        .query("SELECT event_name, status FROM _event_outbox ORDER BY created_at", &Params::new())
        .await
        .unwrap();
    assert_eq!(rows.rows.len(), 2, "dos filas en el outbox (venenosa + handler)");
    assert_eq!(rows.rows[0]["event_name"], json!("ob.e"), "la venenosa va primero por created_at");
    assert_eq!(
        rows.rows[0]["status"], json!("pending"),
        "la venenosa se difiere (no delivered ni dead): reintento"
    );
    assert_eq!(rows.rows[1]["event_name"], json!("ob.from_handler"));
    assert_eq!(
        rows.rows[1]["status"], json!("delivered"),
        "el evento del handler se entregó pese a la fila que falla antes en el lote"
    );
}
