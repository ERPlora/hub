//! ADR-0146 — la sesión de servicio es la fuente de verdad de la sala.
//!
//! Etapa 1: SOLO esquema, migración/backfill e invariantes de `tables_session_assignment`. No se
//! tocan los comandos ni se retira nada de lo anterior hasta que esto esté verde.
//!
//! Por qué existe esta tabla: `tables_session.table_id` solo sabe **dónde está ahora** una cuenta.
//! Al mover de la mesa 12 a la 8 se sobrescribe y el paso por la 12 desaparece — justo lo que hace
//! falta para saber cuánto estuvo ocupada cada mesa. El historial es append-only: cada tramo se
//! abre con su motivo y se cierra con el suyo (`assignment_reason` / `release_reason`), así aparcar
//! solo CIERRA el tramo vivo y no hay que inventar una fila para el periodo aparcado.

use std::path::PathBuf;

use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::Runtime;
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../modules-workspace/modules").join(name)
}

/// Runtime con `tables` instalado (no depende de nadie).
async fn fresh() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    rt.install_from_dir(&mdir("tables")).await.expect("instalar tables");
    // Las mesas del ejemplo: `tables_session` tiene FK interna a `tables_table`.
    for (id, numero) in [("m12", "12"), ("m8", "8")] {
        rt.db_for_test()
            .execute(
                "INSERT INTO tables_table (id, hub_id, number, name, capacity, is_deleted, created_at)
                 VALUES (:id, 'h1', :numero, :nombre, 4, 0, '2026-07-19T00:00:00+00:00')",
                &params(json!({ "id": id, "numero": numero, "nombre": format!("Mesa {numero}") })),
            )
            .await
            .expect("mesa de ejemplo");
    }
    rt
}

/// Inserta una sesión «de antes», como las que ya existen en los hubs en marcha.
async fn sesion_legacy(rt: &Runtime, id: &str, table_id: &str, abierta: &str, cerrada: Option<&str>) {
    rt.db_for_test()
        .execute(
            "INSERT INTO tables_session (id, hub_id, table_id, opened_at, closed_at, guests_count,
                 status, notes, is_deleted, created_at)
             VALUES (:id, 'h1', :table_id, :opened_at, :closed_at, 2, :status, '', 0, :opened_at)",
            &params(json!({
                "id": id, "table_id": table_id, "opened_at": abierta, "closed_at": cerrada,
                "status": if cerrada.is_some() { "closed" } else { "active" },
            })),
        )
        .await
        .expect("sesión legacy");
}

async fn asignacion(
    rt: &Runtime, id: &str, session_id: &str, table_id: &str, op: &str, released: Option<&str>,
) -> Result<(), String> {
    rt.db_for_test()
        .execute(
            "INSERT INTO tables_session_assignment (id, hub_id, session_id, table_id, assigned_at,
                 released_at, assignment_reason, release_reason, operation_id, is_deleted, created_at)
             VALUES (:id, 'h1', :session_id, :table_id, '2026-07-19T20:00:00+00:00', :released,
                     'assigned', :release_reason, :op, 0, '2026-07-19T20:00:00+00:00')",
            &params(json!({
                "id": id, "session_id": session_id, "table_id": table_id, "op": op,
                "released": released,
                "release_reason": if released.is_some() { "moved" } else { "" },
            })),
        )
        .await
        .map(|_| ())
        .map_err(|e| e.to_string())
}

async fn contar(rt: &Runtime, sql: &str) -> i64 {
    let res = rt.db_for_test().query(sql, &Params::new()).await.expect("consulta");
    res.rows
        .first()
        .and_then(|r| r.as_object())
        .and_then(|o| o.values().next().cloned())
        .and_then(|v| v.as_i64())
        .unwrap_or(-1)
}

#[tokio::test]
async fn la_tabla_de_historial_existe_y_admite_un_tramo() {
    let rt = fresh().await;
    sesion_legacy(&rt, "s1", "m12", "2026-07-19T20:00:00+00:00", None).await;
    asignacion(&rt, "a1", "s1", "m12", "op-1", None).await.expect("un tramo vivo");
    assert_eq!(contar(&rt, "SELECT COUNT(*) FROM tables_session_assignment").await, 1);
}

#[tokio::test]
async fn una_sesion_no_puede_tener_dos_tramos_vivos_a_la_vez() {
    // Es LA invariante: una cuenta está en una mesa, no en dos. Sin esto volveríamos al fallo que
    // motivó el ADR — tres mesas ocupadas por el mismo pedido y ninguna liberándose.
    let rt = fresh().await;
    sesion_legacy(&rt, "s1", "m12", "2026-07-19T20:00:00+00:00", None).await;
    asignacion(&rt, "a1", "s1", "m12", "op-1", None).await.expect("el primero entra");

    let err = asignacion(&rt, "a2", "s1", "m8", "op-2", None).await;
    assert!(err.is_err(), "no puede haber dos tramos sin cerrar para la misma sesión");

    // Cerrando el primero, el segundo sí entra: eso es exactamente «mover de mesa».
    rt.db_for_test()
        .execute(
            "UPDATE tables_session_assignment SET released_at = '2026-07-19T20:45:00+00:00',
                 release_reason = 'moved' WHERE id = 'a1'",
            &Params::new(),
        )
        .await
        .unwrap();
    asignacion(&rt, "a2", "s1", "m8", "op-2", None).await.expect("tras cerrar el anterior, entra");
    assert_eq!(contar(&rt, "SELECT COUNT(*) FROM tables_session_assignment").await, 2);
}

#[tokio::test]
async fn el_mismo_operation_id_no_se_escribe_dos_veces() {
    // Idempotencia: el relay puede reentregar y el camarero puede tocar dos veces. Un `operation_id`
    // repetido es la MISMA operación, no dos tramos.
    let rt = fresh().await;
    sesion_legacy(&rt, "s1", "m12", "2026-07-19T20:00:00+00:00", None).await;
    asignacion(&rt, "a1", "s1", "m12", "op-1", Some("2026-07-19T20:45:00+00:00")).await.unwrap();

    let repe = asignacion(&rt, "a2", "s1", "m8", "op-1", None).await;
    assert!(repe.is_err(), "el mismo operation_id no puede crear otro tramo");
}

#[tokio::test]
async fn un_motivo_inventado_se_rechaza() {
    // El motivo lo deriva el handler de un juego cerrado (ADR-0146). Si alguien escribe cualquier
    // cosa, el historial queda contado pero no explicado.
    let rt = fresh().await;
    sesion_legacy(&rt, "s1", "m12", "2026-07-19T20:00:00+00:00", None).await;
    let err = rt
        .db_for_test()
        .execute(
            "INSERT INTO tables_session_assignment (id, hub_id, session_id, table_id, assigned_at,
                 assignment_reason, release_reason, operation_id, is_deleted, created_at)
             VALUES ('a9', 'h1', 's1', 'm12', '2026-07-19T20:00:00+00:00', 'porque-si', '', 'op-9', 0,
                     '2026-07-19T20:00:00+00:00')",
            &Params::new(),
        )
        .await;
    assert!(err.is_err(), "un motivo fuera del juego cerrado se rechaza");
}

#[tokio::test]
async fn el_backfill_da_historial_a_las_sesiones_que_YA_existian() {
    // Los hubs en marcha tienen sesiones sin historial. La migración les crea su primer tramo, o
    // esas mesas quedarían fuera de las estadísticas para siempre.
    let rt = fresh().await;
    sesion_legacy(&rt, "s-viva", "m12", "2026-07-19T20:00:00+00:00", None).await;
    sesion_legacy(&rt, "s-cerrada", "m8", "2026-07-19T18:00:00+00:00", Some("2026-07-19T19:30:00+00:00")).await;

    let backfill = std::fs::read_to_string(
        mdir("tables").join("migrations/postgres/005_session_assignment.sql"),
    )
    .expect("la migración 005");
    // Se queda solo con el INSERT del backfill: fuera los comentarios (van antes de la sentencia,
    // así que sin quitarlos el trozo no «empieza por INSERT») y el resto de DDL.
    let sin_comentarios: String = backfill
        .lines()
        .filter(|l| !l.trim_start().starts_with("--"))
        .collect::<Vec<_>>()
        .join("\n");
    let backfill = sin_comentarios
        .split(';')
        .map(str::trim)
        .filter(|s| s.to_uppercase().starts_with("INSERT"))
        .collect::<Vec<_>>()
        .join(";");
    assert!(!backfill.is_empty(), "la migración debe traer su backfill");

    // Se ejecuta DOS veces: un backfill que duplica al reaplicarse es peor que no tenerlo.
    for _ in 0..2 {
        rt.db_for_test().execute(&backfill, &Params::new()).await.expect("backfill");
    }

    assert_eq!(
        contar(&rt, "SELECT COUNT(*) FROM tables_session_assignment").await,
        2,
        "una fila por sesión, y reaplicar no duplica"
    );
    assert_eq!(
        contar(
            &rt,
            "SELECT COUNT(*) FROM tables_session_assignment
             WHERE session_id = 's-viva' AND released_at IS NULL AND assignment_reason = 'opened'"
        )
        .await,
        1,
        "la sesión viva queda con su tramo ABIERTO"
    );
    assert_eq!(
        contar(
            &rt,
            "SELECT COUNT(*) FROM tables_session_assignment
             WHERE session_id = 's-cerrada' AND released_at = '2026-07-19T19:30:00+00:00'
               AND release_reason = 'closed'"
        )
        .await,
        1,
        "la cerrada queda con su tramo cerrado a la hora en que se cerró"
    );
}

// ── Etapa 2: los COMANDOS escriben historial y proyección en la misma transacción ─────────────
//
// El historial no puede depender de que alguien se acuerde de escribirlo aparte: si la sesión y su
// tramo no se escriben juntos, se desincronizan y el historial deja de ser fuente de verdad.

fn admin() -> erplora_runtime::RequestContext {
    erplora_runtime::RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn tramos(rt: &Runtime, session_id: &str) -> Vec<(String, String, bool)> {
    let res = rt
        .db_for_test()
        .query(
            "SELECT table_id, assignment_reason, release_reason, released_at
             FROM tables_session_assignment WHERE session_id = :sid ORDER BY assigned_at, rowid",
            &params(json!({ "sid": session_id })),
        )
        .await
        .expect("tramos");
    res.rows
        .iter()
        .map(|r| {
            let o = r.as_object().unwrap();
            (
                o["table_id"].as_str().unwrap_or("").to_string(),
                o["assignment_reason"].as_str().unwrap_or("").to_string(),
                o["released_at"].is_null(),
            )
        })
        .collect()
}

/// Abre una sesión en una mesa y devuelve su id.
async fn abrir(rt: &mut Runtime, table_id: &str) -> String {
    rt.execute_command("tables.sessions.open", &params(json!({ "table_id": table_id })), &admin())
        .await
        .expect("abrir sesión");
    let res = rt
        .db_for_test()
        .query(
            "SELECT id FROM tables_session WHERE table_id = :t AND status = 'active'",
            &params(json!({ "t": table_id })),
        )
        .await
        .unwrap();
    res.rows[0].as_object().unwrap()["id"].as_str().unwrap().to_string()
}

#[tokio::test]
async fn abrir_una_sesion_estrena_su_tramo() {
    let mut rt = fresh().await;
    let sid = abrir(&mut rt, "m12").await;
    assert_eq!(
        tramos(&rt, &sid).await,
        vec![("m12".to_string(), "opened".to_string(), true)],
        "la apertura deja UN tramo vivo, con motivo `opened`"
    );
}

#[tokio::test]
async fn cerrar_la_sesion_cierra_su_tramo() {
    // Al cobrar se cierra la sesión: el tramo tiene que cerrarse CON ella, o la mesa quedaría
    // ocupada para siempre en las estadísticas.
    let mut rt = fresh().await;
    let sid = abrir(&mut rt, "m12").await;
    rt.execute_command("tables.sessions.close", &params(json!({ "session_id": sid })), &admin())
        .await
        .expect("cerrar");

    let t = tramos(&rt, &sid).await;
    assert_eq!(t.len(), 1);
    assert!(!t[0].2, "el tramo queda CERRADO");
    let res = rt
        .db_for_test()
        .query(
            "SELECT release_reason FROM tables_session_assignment WHERE session_id = :sid",
            &params(json!({ "sid": sid })),
        )
        .await
        .unwrap();
    assert_eq!(res.rows[0].as_object().unwrap()["release_reason"], json!("closed"));
}

#[tokio::test]
async fn transferir_cierra_un_tramo_y_abre_el_siguiente() {
    // Mover una cuenta de la 12 a la 8 es exactamente esto: el historial conserva AMBOS tramos, que
    // es lo que una columna `table_id` sola no puede dar.
    let mut rt = fresh().await;
    let sid = abrir(&mut rt, "m12").await;
    rt.execute_command(
        "tables.sessions.transfer",
        &params(json!({ "session_id": sid, "target_table_id": "m8" })),
        &admin(),
    )
    .await
    .expect("transferir");

    // La sesión nueva es otra fila; el historial se sigue por la mesa, no por la sesión.
    let res = rt
        .db_for_test()
        .query(
            "SELECT table_id, assignment_reason, release_reason, released_at IS NULL AS vivo
             FROM tables_session_assignment ORDER BY assigned_at, rowid",
            &Params::new(),
        )
        .await
        .unwrap();
    let filas: Vec<(String, String, String)> = res
        .rows
        .iter()
        .map(|r| {
            let o = r.as_object().unwrap();
            (
                o["table_id"].as_str().unwrap_or("").to_string(),
                o["assignment_reason"].as_str().unwrap_or("").to_string(),
                o["release_reason"].as_str().unwrap_or("").to_string(),
            )
        })
        .collect();
    assert_eq!(filas.len(), 2, "quedan los dos tramos: {filas:?}");
    assert_eq!(filas[0], ("m12".into(), "opened".into(), "transferred".into()));
    assert_eq!(filas[1].0, "m8");
    assert_eq!(filas[1].1, "transferred");
}

// ── Etapa 3: la mesa se libera SOLA cuando el pedido termina ──────────────────────────────────
//
// Hasta ahora alguien tenía que acordarse de cerrar la sesión, y cuando no lo hacía la mesa se
// quedaba ocupada para siempre (el fallo que motivó el ADR). Ahora lo dispara el propio pedido.
//
// Ojo al split-bill: `sale.completed` se emite TAMBIÉN en un cobro parcial, donde el pedido sigue
// abierto y la mesa NO debe liberarse. Por eso `tables` escucha el fin del PEDIDO, no el de la venta.

async fn con_pos() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    for m in ["taxes", "inventory", "sales", "tables"] {
        rt.install_from_dir(&mdir(m)).await.unwrap_or_else(|e| panic!("instalar {m}: {e}"));
    }
    rt.db_for_test()
        .execute(
            "INSERT INTO tables_table (id, hub_id, number, name, capacity, is_deleted, created_at)
             VALUES ('m12', 'h1', '12', 'Mesa 12', 4, 0, '2026-07-19T00:00:00+00:00')",
            &Params::new(),
        )
        .await
        .unwrap();
    rt
}

async fn estado_mesa(rt: &Runtime, id: &str) -> String {
    let res = rt
        .db_for_test()
        .query("SELECT status FROM tables_table WHERE id = :id", &params(json!({ "id": id })))
        .await
        .unwrap();
    res.rows[0].as_object().unwrap()["status"].as_str().unwrap_or("").to_string()
}

#[tokio::test]
async fn cobrar_el_pedido_libera_la_mesa_y_cierra_su_tramo() {
    if !mdir("sales").join("dist/handler.wasm").exists() { eprintln!("SKIP"); return; }
    let mut rt = con_pos().await;
    let ctx = admin();

    let sid = abrir(&mut rt, "m12").await;
    let res = rt
        .execute_command(
            "sales.order.open",
            &params(json!({ "items": [{ "product_name": "Caña", "price": 250, "quantity": 1 }] })),
            &ctx,
        )
        .await
        .unwrap();
    let oid = res["new_ids"][0].as_str().unwrap().to_string();
    rt.execute_command(
        "tables.sessions.link_order",
        &params(json!({ "table_id": "m12", "order_id": oid })),
        &ctx,
    )
    .await
    .unwrap();
    assert_eq!(estado_mesa(&rt, "m12").await, "occupied");

    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "order_id": oid, "amount_tendered": 250, "tax_included": true,
            "items": [{ "product_name": "Caña", "price": 250, "quantity": 1, "tax_rate": 21.0 }]
        })),
        &ctx,
    )
    .await
    .expect("cobrar");
    rt.drain_outbox().await.unwrap();

    assert_eq!(estado_mesa(&rt, "m12").await, "available", "cobrar libera la mesa, sin que nadie la cierre a mano");
    let t = tramos(&rt, &sid).await;
    assert!(!t[0].2, "y su tramo queda cerrado: {t:?}");
}

#[tokio::test]
async fn un_cobro_PARCIAL_no_libera_la_mesa() {
    // Split-bill: uno de la mesa paga lo suyo y los demás siguen sentados. Si esto liberase la mesa,
    // el resto de la cuenta se quedaría huérfana.
    if !mdir("sales").join("dist/handler.wasm").exists() { eprintln!("SKIP"); return; }
    let mut rt = con_pos().await;
    let ctx = admin();

    abrir(&mut rt, "m12").await;
    let res = rt
        .execute_command(
            "sales.order.open",
            &params(json!({ "items": [{ "product_name": "Caña", "price": 250, "quantity": 2 }] })),
            &ctx,
        )
        .await
        .unwrap();
    let oid = res["new_ids"][0].as_str().unwrap().to_string();
    rt.execute_command(
        "tables.sessions.link_order",
        &params(json!({ "table_id": "m12", "order_id": oid })),
        &ctx,
    )
    .await
    .unwrap();

    rt.execute_command(
        "sales.complete_sale",
        &params(json!({
            "order_id": oid, "keep_order_open": true, "amount_tendered": 250, "tax_included": true,
            "items": [{ "product_name": "Caña", "price": 250, "quantity": 1, "tax_rate": 21.0 }]
        })),
        &ctx,
    )
    .await
    .expect("cobro parcial");
    rt.drain_outbox().await.unwrap();

    assert_eq!(estado_mesa(&rt, "m12").await, "occupied", "la mesa sigue ocupada: aún queda cuenta");
}

// ── Etapa 4: aparcar = soltar la mesa sin cerrar la cuenta ────────────────────────────────────

#[tokio::test]
async fn aparcar_suelta_la_mesa_y_cierra_el_tramo_sin_cerrar_la_sesion() {
    // Aparcar NO abre un tramo nuevo: cierra el vivo con motivo `parked`. Así el periodo aparcado
    // no tiene que inventarse una asignación a ninguna mesa (ADR-0146).
    let mut rt = fresh().await;
    let sid = abrir(&mut rt, "m12").await;

    rt.execute_command("tables.sessions.park", &params(json!({ "session_id": sid })), &admin())
        .await
        .expect("aparcar");

    assert_eq!(estado_mesa(&rt, "m12").await, "available", "la mesa queda libre para otros");
    let res = rt
        .db_for_test()
        .query(
            "SELECT s.status AS sesion, a.release_reason AS motivo, a.released_at IS NOT NULL AS cerrado
             FROM tables_session s JOIN tables_session_assignment a ON a.session_id = s.id
             WHERE s.id = :sid",
            &params(json!({ "sid": sid })),
        )
        .await
        .unwrap();
    let o = res.rows[0].as_object().unwrap().clone();
    assert_eq!(o["sesion"], json!("parked"), "la CUENTA sigue viva, solo sin mesa");

    // La ocupación NO se lee de `tables_session.table_id` —que conserva la última mesa como
    // referencia para recuperar la cuenta— sino de si hay TRAMO VIVO. Esa es la invariante que
    // importa, y es la que hace innecesario volver la columna anulable.
    assert_eq!(
        contar(&rt, "SELECT COUNT(*) FROM tables_session_assignment WHERE released_at IS NULL AND is_deleted = 0").await,
        0,
        "aparcada = sin tramo vivo = sin ocupar ninguna mesa"
    );
    // `table_id` = mesa ACTUAL. Aparcada no está en ninguna, y la columna lo dice: NULL. Así no hay
    // que recordar para siempre que «significa la última mesa, no donde está».
    let res2 = rt
        .db_for_test()
        .query("SELECT table_id FROM tables_session WHERE id = :sid", &params(json!({ "sid": sid })))
        .await
        .unwrap();
    assert!(res2.rows[0].as_object().unwrap()["table_id"].is_null(),
            "una cuenta aparcada no está en ninguna mesa");
    assert_eq!(o["motivo"], json!("parked"));
    assert_eq!(tramos(&rt, &sid).await.len(), 1, "aparcar no inventa un tramo nuevo");
}

#[tokio::test]
async fn restaurar_una_cuenta_aparcada_estrena_tramo_en_la_mesa_nueva() {
    // La recuperas en otra mesa: el historial encadena 12 → (aparcada) → 8, sin fingir que estuvo
    // en ninguna mesa mientras esperaba.
    let mut rt = fresh().await;
    let sid = abrir(&mut rt, "m12").await;
    rt.execute_command("tables.sessions.park", &params(json!({ "session_id": sid })), &admin())
        .await
        .unwrap();

    rt.execute_command(
        "tables.sessions.restore",
        &params(json!({ "session_id": sid, "table_id": "m8" })),
        &admin(),
    )
    .await
    .expect("restaurar");

    let t = tramos(&rt, &sid).await;
    assert_eq!(t.len(), 2, "un tramo por estancia: {t:?}");
    assert_eq!(t[1], ("m8".to_string(), "restored".to_string(), true));
    assert_eq!(estado_mesa(&rt, "m8").await, "occupied");
    assert_eq!(estado_mesa(&rt, "m12").await, "available");
}

#[tokio::test]
async fn una_cuenta_aparcada_no_ocupa_ninguna_mesa() {
    // Invariante de sala: mientras está aparcada, ninguna mesa la está esperando.
    let mut rt = fresh().await;
    let sid = abrir(&mut rt, "m12").await;
    rt.execute_command("tables.sessions.park", &params(json!({ "session_id": sid })), &admin())
        .await
        .unwrap();
    let ocupadas = contar(
        &rt,
        "SELECT COUNT(*) FROM tables_session_assignment WHERE released_at IS NULL AND is_deleted = 0",
    )
    .await;
    assert_eq!(ocupadas, 0, "sin tramo vivo = sin mesa ocupada");
    let _ = sid;
}


#[tokio::test]
async fn la_reconstruccion_de_la_tabla_no_se_lleva_el_historial() {
    // La migración 006 reconstruye `tables_session` para que `table_id` admita NULL. La trampa: el
    // historial colgaba de ella con una FK ON DELETE CASCADE, así que el DROP implícito del rebuild
    // habría BORRADO el historial entero — la fuente de verdad que este ADR acaba de construir.
    //
    // Por eso la migración reconstruye PRIMERO el historial sin esa FK. Este test lo fija: los
    // tramos sobreviven, y borrar una sesión ya no se lleva su historia por delante.
    let mut rt = fresh().await;
    let sid = abrir(&mut rt, "m12").await;
    rt.execute_command("tables.sessions.park", &params(json!({ "session_id": sid })), &admin())
        .await
        .unwrap();
    rt.execute_command(
        "tables.sessions.restore",
        &params(json!({ "session_id": sid, "table_id": "m8" })),
        &admin(),
    )
    .await
    .unwrap();
    assert_eq!(tramos(&rt, &sid).await.len(), 2, "los dos tramos sobreviven a la reconstrucción");

    rt.db_for_test()
        .execute("DELETE FROM tables_session WHERE id = :sid", &params(json!({ "sid": sid })))
        .await
        .unwrap();
    assert_eq!(
        contar(&rt, "SELECT COUNT(*) FROM tables_session_assignment").await,
        2,
        "el historial no se borra en cascada con la sesión"
    );
}
