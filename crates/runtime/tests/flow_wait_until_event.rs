//! **Esperar hasta una fecha DEL EVENTO, y cancelar o mover esa espera con otro evento** (hub#951).
//!
//! Hasta aquí una espera tenía UNA salida: su reloj. `delay.until` sabía dormir hasta un instante,
//! pero nada podía despertar un run dormido antes de tiempo — así que el recordatorio de una cita
//! cancelada ayer se mandaba igual. El hilo de la comunidad de Square que cita el estudio de
//! mercado es exactamente eso, en un producto de primera línea.
//!
//! La forma es la que gana en el mercado (decisión publicada en la issue, 15/08):
//!
//! - **Scheduled Paths de Salesforce** — el instante sale de un CAMPO del evento (`until`) más un
//!   desplazamiento (`offset_seconds`). «24 h antes de la cita», sin escribir fechas.
//! - **La transición programada de NetSuite SuiteFlow** — la espera es un ESTADO con varias
//!   salidas; el reloj es una de ellas y la primera transición atómica se lleva el run. Eso es lo
//!   que hace que «nunca las dos» no cueste ni un lock: todas las salidas son el MISMO `UPDATE`
//!   condicional, y quien llega segundo afecta cero filas.
//! - **La re-comprobación de Klaviyo** — que aquí NO es un campo: se compone `delay → query`
//!   (hub#954) `→ condition`. Un `cancel_on` se puede perder (evento no emitido, módulo
//!   desinstalado, hub apagado) y mirar otra vez es el remedio; un cuarto campo prometiéndolo
//!   sería un segundo motor al lado de este.
//!
//! Los dos flujos objetivo de la issue son el mismo mecanismo: «recuérdame 24 h antes de la cita,
//! salvo que se cancele o se mueva» y «reclama la factura al vencer, salvo que se pague».
use std::path::PathBuf;

use erplora_db::{testutil::TestDb, Params};
use erplora_runtime::flows::grants::GrantKind;
use erplora_runtime::flows::{def, store, waits, NewFlow};
use erplora_runtime::Runtime;
use serde_json::{json, Value};

const HUB: &str = "hub-wait-951";
const OWNER: &str = "hub_user:owner";

/// La cita: lejos, pero **dentro** del horizonte de 90 días. Relativa al reloj y no una constante,
/// porque el horizonte también lo es — una fecha fija en el fuente sería un test que caduca.
fn appointment() -> String {
    (chrono::Utc::now() + chrono::Duration::days(30)).to_rfc3339()
}

/// Más allá del horizonte de 90 días: la espera que antes dormía para siempre.
const BEYOND_THE_HORIZON: &str = "2999-01-01T10:00:00+00:00";

fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests")
        .join("fixture_flows")
        .join(name)
}

async fn runtime_on(db: erplora_db::PgAdapter, hub_id: &str) -> Runtime {
    let mut rt = Runtime::with_hub_id(Box::new(db), hub_id);
    rt.ensure_system_tables().await.unwrap();
    rt.install_from_dir(&fixture("crm")).await.unwrap();
    rt
}

async fn runtime() -> Runtime {
    runtime_on(TestDb::new().await.adapter().await, HUB).await
}

/// El paso de espera de la issue, con las salidas que se le pidan.
fn wait_step(extra: Value) -> Value {
    let mut step = json!({
        "id": "wait", "kind": "delay",
        "until": "input.appointment_at",
        "offset_seconds": -86400
    });
    let map = step.as_object_mut().unwrap();
    for (k, v) in extra.as_object().unwrap() {
        map.insert(k.clone(), v.clone());
    }
    step
}

/// El recordatorio es un `command` detrás de la espera: el kernel no sabe qué es una cita.
fn definition(step: Value) -> Value {
    json!({
        "schema_version": 1,
        "steps": [step, {
            "id": "remind", "kind": "command", "command": "crm.note.add",
            "params": { "text": "recordatorio de la cita {{input.appointment_id}}" }
        }]
    })
}

fn cancel_hook() -> Value {
    json!([{
        "event": "appointment.cancelled",
        "correlate": { "event.id": "input.appointment_id" }
    }])
}

fn reschedule_hook() -> Value {
    json!([{
        "event": "appointment.rescheduled",
        "correlate": { "event.id": "input.appointment_id" },
        "until": "event.appointment_at"
    }])
}

/// Crea el flujo, le concede la escritura de después y arranca un run que llega a dormir.
async fn sleeping(rt: &Runtime, step: Value) -> (String, String) {
    sleeping_with(
        rt,
        step,
        json!({ "appointment_at": appointment(), "appointment_id": "a-42" }),
    )
    .await
}

async fn sleeping_with(rt: &Runtime, step: Value, input: Value) -> (String, String) {
    let flow_id = rt
        .create_flow(
            &NewFlow {
                name: "Recordar cita".into(),
                enabled: true,
                definition: definition(step),
            },
            OWNER,
        )
        .await
        .unwrap()
        .id;
    rt.replace_flow_grants(
        &flow_id,
        &[(GrantKind::Command, "crm.note.add".into())],
        OWNER,
    )
    .await
    .unwrap();
    let run_id = rt.start_flow_run(&flow_id, &input, OWNER).await.unwrap();
    rt.process_flows().await.unwrap();
    (flow_id, run_id)
}

/// Un evento del hub, entregado por el relay como cualquier otro.
async fn deliver(rt: &Runtime, hub_id: &str, id: &str, name: &str, payload: Value) {
    let mut p = Params::new();
    p.insert("id".into(), json!(id));
    p.insert("hub_id".into(), json!(hub_id));
    p.insert("event_name".into(), json!(name));
    p.insert("payload".into(), json!(payload.to_string()));
    p.insert("now".into(), json!("2026-08-15T10:00:00+00:00"));
    rt.db_for_test()
        .execute(
            "INSERT INTO _event_outbox \
             (id, hub_id, user_id, permissions, event_name, module_id, payload, depth, status, \
              attempts, next_attempt_at, last_error, created_at) \
             VALUES (:id, :hub_id, '', '[]', :event_name, 'agenda', :payload, 0, 'pending', 0, \
                     :now, '', :now)",
            &p,
        )
        .await
        .unwrap();
    rt.drain_outbox().await.unwrap();
}

async fn status(rt: &Runtime, run_id: &str) -> String {
    rt.get_flow_run(run_id).await.unwrap().0.status
}

async fn wake_at(rt: &Runtime, run_id: &str) -> Option<String> {
    rt.get_flow_run(run_id).await.unwrap().0.wake_at
}

async fn notes(rt: &Runtime) -> Vec<String> {
    rt.db_for_test()
        .query("SELECT text FROM crm_note ORDER BY text", &Params::new())
        .await
        .unwrap()
        .rows
        .iter()
        .map(|r| r["text"].as_str().unwrap_or_default().to_string())
        .collect()
}

async fn armed(rt: &Runtime, run_id: &str) -> i64 {
    let mut p = Params::new();
    p.insert("r".into(), json!(run_id));
    rt.db_for_test()
        .query(
            "SELECT COUNT(*) AS c FROM _flow_run_waits \
             WHERE run_id = :r AND status = 'armed' AND deleted_at IS NULL",
            &p,
        )
        .await
        .unwrap()
        .rows[0]["c"]
        .as_i64()
        .unwrap_or(-1)
}

/// Adelanta el reloj de la espera hasta el pasado, que es lo que hace el tiempo.
async fn ring_the_clock(rt: &Runtime, run_id: &str) {
    let mut p = Params::new();
    p.insert("id".into(), json!(run_id));
    rt.db_for_test()
        .execute(
            "UPDATE _flow_runs SET wake_at = '2020-01-01T00:00:00+00:00' WHERE id = :id",
            &p,
        )
        .await
        .unwrap();
}

// ── el instante viene del evento, desplazado ──────────────────────────────────────────────────

/// El paso 1 de la decisión: el instante sale de un campo del run y `offset_seconds` lo mueve.
/// 24 h antes de la cita, calculado por el hub y no escrito a mano.
#[tokio::test]
async fn la_espera_se_arma_veinticuatro_horas_antes_del_instante_del_evento() {
    let rt = runtime().await;
    // La cita se escribe en la zona del negocio, que es como llega en un payload real; lo que se
    // persiste tiene que ser el mismo INSTANTE en UTC (hub#970), no el mismo texto.
    let cita = (chrono::Utc::now() + chrono::Duration::days(30))
        .with_timezone(&chrono::FixedOffset::east_opt(2 * 3600).unwrap())
        .to_rfc3339();
    let (_, run_id) = sleeping_with(
        &rt,
        wait_step(json!({})),
        json!({ "appointment_at": cita.clone(), "appointment_id": "a-42" }),
    )
    .await;

    assert_eq!(status(&rt, &run_id).await, store::STATUS_SLEEPING);
    let armed_at = wake_at(&rt, &run_id)
        .await
        .expect("duerme como una fila con `wake_at`");
    assert_eq!(
        armed_at,
        (chrono::DateTime::parse_from_rfc3339(&cita)
            .unwrap()
            .with_timezone(&chrono::Utc)
            - chrono::Duration::seconds(86400))
        .to_rfc3339(),
        "el desplazamiento se aplica al instante del evento, y se persiste en UTC (hub#970)"
    );
    assert!(
        armed_at.ends_with("+00:00"),
        "UTC dentro, la zona del negocio en pantalla"
    );
    assert!(
        notes(&rt).await.is_empty(),
        "lo que espera es el recordatorio"
    );
}

// ── cancelar ──────────────────────────────────────────────────────────────────────────────────

/// **El caso literal de la issue.** Una cita cancelada no recibe recordatorio.
#[tokio::test]
async fn una_cita_cancelada_no_recibe_su_recordatorio() {
    let rt = runtime().await;
    let (_, run_id) = sleeping(&rt, wait_step(json!({ "cancel_on": cancel_hook() }))).await;
    assert_eq!(
        armed(&rt, &run_id).await,
        1,
        "la espera queda armada al dormirse"
    );

    deliver(
        &rt,
        HUB,
        "evt-cancel",
        "appointment.cancelled",
        json!({ "id": "a-42" }),
    )
    .await;

    assert_eq!(
        status(&rt, &run_id).await,
        store::STATUS_CANCELLED,
        "el evento saca el run del estado de espera"
    );
    assert_eq!(
        wake_at(&rt, &run_id).await,
        None,
        "y deja de estar «esperando a despertar»"
    );
    assert_eq!(
        armed(&rt, &run_id).await,
        0,
        "sus esperas se desarman con él"
    );

    // Y el reloj ya no puede resucitarlo: ni el tick posterior escribe el recordatorio.
    rt.process_flows().await.unwrap();
    assert!(
        notes(&rt).await.is_empty(),
        "una cita cancelada NO recibe recordatorio"
    );
}

/// La correlación es lo que hace que «esta cita» signifique esta. Sin ella, la primera cancelación
/// de cualquier cita se llevaría por delante todos los recordatorios armados del hub.
#[tokio::test]
async fn la_cancelacion_de_otra_cita_deja_la_espera_intacta() {
    let rt = runtime().await;
    let (_, run_id) = sleeping(&rt, wait_step(json!({ "cancel_on": cancel_hook() }))).await;

    deliver(
        &rt,
        HUB,
        "evt-other",
        "appointment.cancelled",
        json!({ "id": "a-99" }),
    )
    .await;

    assert_eq!(status(&rt, &run_id).await, store::STATUS_SLEEPING);
    assert_eq!(armed(&rt, &run_id).await, 1, "la espera sigue armada");

    // Control positivo en el mismo test: el mecanismo SÍ dispara cuando el id es el suyo. Sin
    // esto, un fallo que no cancelara nunca pasaría por «aislamiento correcto».
    deliver(
        &rt,
        HUB,
        "evt-mine",
        "appointment.cancelled",
        json!({ "id": "a-42" }),
    )
    .await;
    assert_eq!(status(&rt, &run_id).await, store::STATUS_CANCELLED);
}

/// El relay es at-least-once: el mismo evento VUELVE. Cancelar dos veces tiene que ser cancelar
/// una — la idempotencia va por el listener sintético `_flow_wait:<id>` en `_event_delivery`,
/// el patrón exacto de `_flow:<trigger_id>`.
#[tokio::test]
async fn el_mismo_evento_cancelador_entregado_dos_veces_cancela_una_vez() {
    let rt = runtime().await;
    let (_, run_id) = sleeping(&rt, wait_step(json!({ "cancel_on": cancel_hook() }))).await;

    deliver(
        &rt,
        HUB,
        "evt-cancel",
        "appointment.cancelled",
        json!({ "id": "a-42" }),
    )
    .await;
    let first = rt.get_flow_run(&run_id).await.unwrap().0;

    // El mismo id de evento, reintentado por el relay.
    let mut p = Params::new();
    p.insert("id".into(), json!("evt-cancel"));
    rt.db_for_test()
        .execute(
            "UPDATE _event_outbox SET status = 'pending', next_attempt_at = created_at \
             WHERE id = :id",
            &p,
        )
        .await
        .unwrap();
    rt.drain_outbox().await.unwrap();

    let second = rt.get_flow_run(&run_id).await.unwrap().0;
    assert_eq!(second.status, store::STATUS_CANCELLED);
    assert_eq!(
        second.finished_at, first.finished_at,
        "la segunda entrega no vuelve a cerrar el run"
    );
}

/// **La carrera.** El criterio de la issue: «una transición atómica gana, nunca ambas». No hay
/// lock: la cancelación y el reloj escriben el MISMO `UPDATE` condicional, y quien llega segundo
/// afecta cero filas. Aquí el reloj llega primero.
#[tokio::test]
async fn si_el_reloj_gana_la_cancelacion_posterior_no_toca_el_run() {
    let rt = runtime().await;
    let (_, run_id) = sleeping(&rt, wait_step(json!({ "cancel_on": cancel_hook() }))).await;

    ring_the_clock(&rt, &run_id).await;
    rt.process_flows().await.unwrap();
    assert_eq!(
        status(&rt, &run_id).await,
        store::STATUS_DONE,
        "el reloj ganó y el run terminó"
    );
    assert_eq!(notes(&rt).await.len(), 1, "el recordatorio salió");

    // La cancelación llega tarde. No puede deshacer un run terminado ni marcarlo cancelado.
    deliver(
        &rt,
        HUB,
        "evt-cancel",
        "appointment.cancelled",
        json!({ "id": "a-42" }),
    )
    .await;
    assert_eq!(status(&rt, &run_id).await, store::STATUS_DONE);
    assert_eq!(
        notes(&rt).await.len(),
        1,
        "y desde luego no manda un segundo recordatorio"
    );
}

// ── reprogramar ───────────────────────────────────────────────────────────────────────────────

/// Mover la cita mueve la espera, **y no deja el timer antiguo** — que es un criterio de aceptación
/// de la issue. No lo deja porque no hay cola de timers: un run dormido tiene UN `wake_at`, y
/// moverlo es escribir una columna.
#[tokio::test]
async fn reprogramar_la_cita_mueve_la_espera_y_no_deja_el_reloj_viejo() {
    let rt = runtime().await;
    let (_, run_id) = sleeping(
        &rt,
        wait_step(json!({ "reschedule_on": reschedule_hook() })),
    )
    .await;
    let before = wake_at(&rt, &run_id).await.unwrap();

    let moved = (chrono::Utc::now() + chrono::Duration::days(45)).to_rfc3339();
    deliver(
        &rt,
        HUB,
        "evt-move",
        "appointment.rescheduled",
        json!({ "id": "a-42", "appointment_at": moved.clone() }),
    )
    .await;

    let after = wake_at(&rt, &run_id)
        .await
        .expect("sigue dormido, con otro instante");
    assert_ne!(after, before);
    assert_eq!(
        after,
        chrono::DateTime::parse_from_rfc3339(&moved)
            .unwrap()
            .with_timezone(&chrono::Utc)
            .checked_sub_signed(chrono::Duration::seconds(86400))
            .unwrap()
            .to_rfc3339(),
        "«24 h antes» SIGUE siendo 24 h antes cuando la cita se mueve: el offset se reaplica"
    );
    assert_eq!(status(&rt, &run_id).await, store::STATUS_SLEEPING);
    assert_eq!(
        armed(&rt, &run_id).await,
        1,
        "y la espera sigue armada por si vuelve a moverse"
    );

    // Y al llegar el nuevo instante, el recordatorio sale una sola vez.
    ring_the_clock(&rt, &run_id).await;
    rt.process_flows().await.unwrap();
    assert_eq!(notes(&rt).await.len(), 1);
}

/// Un evento que no para de llegar empujaría la misma espera hacia adelante para siempre y el run
/// no acabaría nunca. Es la guarda de `MAX_RUNS_PER_MINUTE`, un nivel más abajo.
#[tokio::test]
async fn una_espera_movida_demasiadas_veces_para_de_moverse() {
    let rt = runtime().await;
    let (_, run_id) = sleeping(
        &rt,
        wait_step(json!({ "reschedule_on": reschedule_hook() })),
    )
    .await;

    for i in 0..=def::MAX_RESCHEDULES {
        deliver(
            &rt,
            HUB,
            &format!("evt-move-{i}"),
            "appointment.rescheduled",
            json!({ "id": "a-42", "appointment_at": appointment() }),
        )
        .await;
    }

    assert_eq!(status(&rt, &run_id).await, store::STATUS_FAILED);
    let why = rt.get_flow_run(&run_id).await.unwrap().0.last_error;
    assert!(why.contains(def::ERR_MAX_RESCHEDULES), "{why}");
    assert_eq!(armed(&rt, &run_id).await, 0, "y deja de escuchar");
}

/// Las dos salidas conviven en el mismo paso, y la primera que dispara se lleva el run: la de
/// SuiteFlow, «del mismo estado salen la programada y las de evento».
#[tokio::test]
async fn cancelar_y_reprogramar_conviven_y_cancelar_desarma_a_su_hermana() {
    let rt = runtime().await;
    let (_, run_id) = sleeping(
        &rt,
        wait_step(json!({ "cancel_on": cancel_hook(), "reschedule_on": reschedule_hook() })),
    )
    .await;
    assert_eq!(armed(&rt, &run_id).await, 2);

    deliver(
        &rt,
        HUB,
        "evt-cancel",
        "appointment.cancelled",
        json!({ "id": "a-42" }),
    )
    .await;
    assert_eq!(status(&rt, &run_id).await, store::STATUS_CANCELLED);
    assert_eq!(
        armed(&rt, &run_id).await,
        0,
        "la hermana se desarma con la que ganó"
    );

    // Y una reprogramación posterior ya no mueve nada.
    deliver(
        &rt,
        HUB,
        "evt-move",
        "appointment.rescheduled",
        json!({ "id": "a-42", "appointment_at": appointment() }),
    )
    .await;
    assert_eq!(status(&rt, &run_id).await, store::STATUS_CANCELLED);
    assert_eq!(wake_at(&rt, &run_id).await, None);
}

// ── el instante ya pasó ───────────────────────────────────────────────────────────────────────

/// Las tres políticas, y el defecto es el restrictivo. Salesforce ejecuta la ruta programada de
/// inmediato; aquí manda la regla propia del kernel (como `policy: manual`), porque el caso literal
/// es un recordatorio cuya hora ya pasó y mandarlo tarde es peor que no mandarlo.
#[tokio::test]
async fn un_instante_ya_vencido_sigue_la_politica_elegida() {
    let past = json!({ "appointment_at": "2020-01-01T10:00:00+00:00", "appointment_id": "a-1" });

    // Por defecto: `skip`. El run termina y el recordatorio no se manda.
    let rt = runtime().await;
    let (_, run_id) = sleeping_with(&rt, wait_step(json!({})), past.clone()).await;
    assert_eq!(status(&rt, &run_id).await, store::STATUS_DONE);
    assert!(
        notes(&rt).await.is_empty(),
        "el recordatorio de una hora que ya pasó no sale"
    );

    // `continue_now`: el comportamiento de Salesforce, para quien lo escriba.
    let rt = runtime().await;
    let (_, run_id) = sleeping_with(
        &rt,
        wait_step(json!({ "past_due_policy": "continue_now" })),
        past.clone(),
    )
    .await;
    assert_eq!(status(&rt, &run_id).await, store::STATUS_DONE);
    assert_eq!(notes(&rt).await.len(), 1, "sigue AHORA, sin dormir");

    // `fail`: para el flujo donde un instante perdido es un problema que alguien tiene que ver.
    let rt = runtime().await;
    let (_, run_id) =
        sleeping_with(&rt, wait_step(json!({ "past_due_policy": "fail" })), past).await;
    assert_eq!(status(&rt, &run_id).await, store::STATUS_FAILED);
    let why = rt.get_flow_run(&run_id).await.unwrap().0.last_error;
    assert!(why.contains(def::ERR_DELAY_PAST_DUE), "{why}");
}

/// El techo. **Antes no había ninguno**: un `until` que resolviera al año 3000 dormía como una fila
/// que todas las reglas de retención eximen a propósito.
#[tokio::test]
async fn una_espera_mas_alla_del_horizonte_para_el_run_en_vez_de_dormir_para_siempre() {
    // Con el techo por defecto (90 días), el año 2999 se para en seco en vez de dormirse.
    let rt = runtime().await;
    let (_, run_id) = sleeping_with(
        &rt,
        wait_step(json!({})),
        json!({ "appointment_at": BEYOND_THE_HORIZON, "appointment_id": "a-1" }),
    )
    .await;
    assert_eq!(status(&rt, &run_id).await, store::STATUS_FAILED);
    let why = rt.get_flow_run(&run_id).await.unwrap().0.last_error;
    assert!(why.contains(def::ERR_DELAY_HORIZON), "{why}");
    assert_eq!(
        wake_at(&rt, &run_id).await,
        None,
        "no queda una fila durmiendo mil años"
    );

    // Y un `max_wait` propio recorta el techo del hub: la misma cita de dentro de 30 días es una
    // espera que este flujo no quiso.
    let rt = runtime().await;
    let (_, run_id) = sleeping_with(
        &rt,
        wait_step(json!({ "max_wait": 3600 })),
        json!({ "appointment_at": appointment(), "appointment_id": "a-1" }),
    )
    .await;
    assert_eq!(status(&rt, &run_id).await, store::STATUS_FAILED);
    let why = rt.get_flow_run(&run_id).await.unwrap().0.last_error;
    assert!(why.contains(def::ERR_DELAY_HORIZON), "{why}");

    // Control positivo: lo que SÍ cabe en el techo sigue durmiendo. Sin esto, un `delay` roto de
    // cualquier otra forma pasaría por «el horizonte funciona».
    let rt = runtime().await;
    let (_, run_id) = sleeping(&rt, wait_step(json!({}))).await;
    assert_eq!(status(&rt, &run_id).await, store::STATUS_SLEEPING);
}

// ── el resto del contrato ─────────────────────────────────────────────────────────────────────

/// Aislamiento de hub **con el vecino VIVO**: el otro hub tiene el mismo flujo, el mismo id de cita
/// y su propia espera armada. Un test sin vecino no prueba nada — no distingue «filtra por
/// `hub_id`» de «no hay nada que filtrar».
#[tokio::test]
async fn la_cancelacion_de_un_hub_no_toca_la_espera_del_vecino() {
    let test_db = TestDb::new().await;
    let mine = runtime_on(test_db.adapter().await, HUB).await;
    let neighbour = runtime_on(test_db.adapter().await, "hub-vecino").await;

    let (_, mine_run) = sleeping(&mine, wait_step(json!({ "cancel_on": cancel_hook() }))).await;
    let (_, their_run) =
        sleeping(&neighbour, wait_step(json!({ "cancel_on": cancel_hook() }))).await;
    assert_eq!(armed(&neighbour, &their_run).await, 1);

    deliver(
        &mine,
        HUB,
        "evt-cancel",
        "appointment.cancelled",
        json!({ "id": "a-42" }),
    )
    .await;

    assert_eq!(status(&mine, &mine_run).await, store::STATUS_CANCELLED);
    assert_eq!(
        status(&neighbour, &their_run).await,
        store::STATUS_SLEEPING,
        "la misma cita, el mismo id, otro negocio: su recordatorio sigue en pie"
    );
    assert_eq!(armed(&neighbour, &their_run).await, 1);
}

/// Borrar el flujo cancela sus runs dormidos (hub#771) — y ahora también desarma sus esperas. Una
/// espera que sobreviviera a su flujo se miraría en cada entrega de su evento, para siempre, y
/// afectaría cero filas cada vez.
#[tokio::test]
async fn borrar_el_flujo_desarma_las_esperas_de_sus_runs() {
    let rt = runtime().await;
    let (flow_id, run_id) = sleeping(&rt, wait_step(json!({ "cancel_on": cancel_hook() }))).await;
    assert_eq!(armed(&rt, &run_id).await, 1);

    rt.delete_flow(&flow_id, OWNER).await.unwrap();

    assert_eq!(status(&rt, &run_id).await, store::STATUS_CANCELLED);
    assert_eq!(armed(&rt, &run_id).await, 0);
}

/// La espera guarda **solo el id correlacionado**, jamás el payload. Es el criterio de retención de
/// la issue, y es comprobable byte a byte: el resto del evento no está en la tabla.
#[tokio::test]
async fn una_espera_armada_no_guarda_el_payload_de_nadie() {
    let rt = runtime().await;
    sleeping_with(
        &rt,
        wait_step(json!({ "cancel_on": cancel_hook() })),
        json!({
            "appointment_at": appointment(), "appointment_id": "a-42",
            "customer_phone": "+34600111222", "customer_name": "Marta Ruiz"
        }),
    )
    .await;

    let row = rt
        .db_for_test()
        .query("SELECT * FROM _flow_run_waits", &Params::new())
        .await
        .unwrap()
        .rows
        .remove(0);
    let dump = row.to_string();
    assert!(
        dump.contains("a-42"),
        "el id correlacionado sí: es para lo que sirve"
    );
    assert!(
        !dump.contains("600111222"),
        "el teléfono del cliente NO: {dump}"
    );
    assert!(!dump.contains("Marta"), "ni su nombre: {dump}");
}

/// El listener sintético vive en el mismo espacio que el de los triggers y no puede chocar con el
/// de un módulo: ningún command empieza por `_`.
#[tokio::test]
async fn la_idempotencia_se_reserva_bajo_un_listener_que_ningun_modulo_puede_usar() {
    let rt = runtime().await;
    let (_, run_id) = sleeping(&rt, wait_step(json!({ "cancel_on": cancel_hook() }))).await;
    deliver(
        &rt,
        HUB,
        "evt-cancel",
        "appointment.cancelled",
        json!({ "id": "a-42" }),
    )
    .await;

    let listeners: Vec<String> = rt
        .db_for_test()
        .query(
            "SELECT listener_command FROM _event_delivery WHERE event_id = 'evt-cancel'",
            &Params::new(),
        )
        .await
        .unwrap()
        .rows
        .iter()
        .map(|r| {
            r["listener_command"]
                .as_str()
                .unwrap_or_default()
                .to_string()
        })
        .collect();
    assert!(
        listeners.iter().any(|l| l.starts_with("_flow_wait:")),
        "la marca de idempotencia va donde va la de un trigger: {listeners:?}"
    );
    assert_eq!(status(&rt, &run_id).await, store::STATUS_CANCELLED);
    // Y el nombre es el que dice el módulo, para que un lector del contrato lo reconozca.
    assert_eq!(waits::synthetic_listener("x"), "_flow_wait:x");
}
