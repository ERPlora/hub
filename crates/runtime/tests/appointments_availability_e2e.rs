//! E2E del MOTOR DE DISPONIBILIDAD del módulo `appointments` (req. de negocio
//! "agenda sin solape por profesional").
//!
//! La disponibilidad autoritativa vive en la query Tier-0 `appointments.availability.check`
//! (SQL declarativo): es el motor que `create`/`reschedule` consultan (por `staff_id`)
//! ANTES de materializar (la UI/SDK lo invoca; el handler WASM no puede precargar lecturas
//! — ADR-0021). Este test ejercita el contrato del motor end-to-end contra SQLite:
//!
//!   1. Solape POR PROFESIONAL respetando la duración del servicio: con
//!      `allow_overlapping=false`, una 2ª cita de la MISMA profesional dentro de
//!      [inicio, inicio+duración) se RECHAZA (`reason='overlap'`).
//!   2. Capacidad = nº de empleados: la misma franja para OTRA profesional se ACEPTA.
//!   3. El toggle `allow_overlapping=true` permite varias citas a la misma hora.
//!   4. Fuera del horario de trabajo (`schedules`/timeslots) se RECHAZA
//!      (`reason='outside_schedule'`).
//!
//! Escenario del requisito: peinado/lavado (30 min) → Peluquera1 @ 12:00 ⇒ P1 ocupada
//! 12:00–12:30; 2ª cita de P1 en esa ventana RECHAZADA; cita de Peluquera2 @ 12:00 ACEPTADA.
//!
//! Fechas: `availability.check` cruza `:now` (lo inyecta el runtime con la hora real del
//! servidor) contra `min_booking_notice`/`max_advance_booking`. Para que el test sea
//! determinista elegimos una fecha futura (un MIÉRCOLES dentro de la ventana de antelación)
//! calculada al vuelo, y fijamos `min_booking_notice=0` en settings.
use std::path::PathBuf;

use chrono::{Datelike, Duration, Utc, Weekday};
use erplora_db::{Params, testutil::fresh_db};
use erplora_runtime::{RequestContext, Runtime};
use serde_json::json;

fn params(v: serde_json::Value) -> Params {
    v.as_object().cloned().unwrap_or_default()
}
fn mdir(n: &str) -> PathBuf {
    erplora_runtime::e2e_support::modules_root().join(n)
}
/// Los módulos reales viven en `modules-workspace/` (repos hermanos), ausentes en CI aislado. Si
/// el handler no está presente, los tests que instalan módulos se OMITEN (mismo patrón que el
/// resto de e2e: inventory/sales/cash_register…).
fn wasm_present() -> bool {
    mdir("appointments").join("dist/handler.wasm").exists()
}
fn admin() -> RequestContext {
    RequestContext::new("h1", "u1", ["*".to_string()])
}

async fn rt_appts() -> Runtime {
    let db = fresh_db().await;
    let mut rt = Runtime::new(Box::new(db));
    // appointments `depends_on` customers + services + staff (FK lógicas cross-módulo; staff por
    // ADR-0074, selector de profesional) y services `depends_on` taxes (ADR-0066); el installer
    // valida la cadena, así que las instalamos en orden topológico primero (staff no depende de nada).
    rt.install_from_dir(&mdir("taxes")).await.expect("instalar taxes");
    rt.install_from_dir(&mdir("customers")).await.expect("instalar customers");
    rt.install_from_dir(&mdir("services")).await.expect("instalar services");
    rt.install_from_dir(&mdir("staff")).await.expect("instalar staff");
    rt.install_from_dir(&mdir("appointments")).await.expect("instalar appointments");
    rt
}

/// Próximo MIÉRCOLES a >=7 días vista (dentro de `max_advance_booking=90`, lejos del
/// borde de `min_booking_notice`). Devuelve `YYYY-MM-DD`.
fn next_wednesday() -> String {
    let mut d = Utc::now().date_naive() + Duration::days(7);
    while d.weekday() != Weekday::Wed {
        d += Duration::days(1);
    }
    d.format("%Y-%m-%d").to_string()
}

/// `available` (0/1) + `reason` de un `availability.check` para un staff y franja.
async fn check(
    rt: &Runtime,
    ctx: &RequestContext,
    start: &str,
    duration: i64,
    staff_id: Option<&str>,
) -> (i64, String) {
    let mut p = json!({ "start_datetime": start, "duration_minutes": duration });
    if let Some(s) = staff_id {
        p["staff_id"] = json!(s);
    }
    let rows = rt
        .execute_query("appointments.availability.check", &params(p), ctx)
        .await
        .expect("availability.check");
    let row = rows.first().expect("availability.check devuelve una fila");
    (row["available"].as_i64().unwrap_or(-1), row["reason"].as_str().unwrap_or("?").to_string())
}

/// Settings del hub con el toggle de solape indicado y sin antelación mínima (determinismo).
async fn set_overlap(rt: &Runtime, ctx: &RequestContext, allow_overlapping: bool) {
    rt.execute_command(
        "appointments.settings.upsert",
        &params(json!({
            "default_duration": 60,
            "min_booking_notice": 0,
            "max_advance_booking": 90,
            "allow_overlapping": allow_overlapping,
            "calendar_start_hour": 8,
            "calendar_end_hour": 20,
            "slot_interval": 15
        })),
        ctx,
    )
    .await
    .expect("settings.upsert");
}

/// Crea un horario de trabajo (lun–vie, 09:00–18:00) con tramos en cada día laborable.
async fn seed_weekday_schedule(rt: &Runtime, ctx: &RequestContext) {
    rt.execute_command(
        "appointments.schedules.create",
        &params(json!({ "name": "Horario salón", "is_default": true })),
        ctx,
    )
    .await
    .expect("schedules.create");
    let schedules = rt
        .execute_query("appointments.schedules.list", &Params::new(), ctx)
        .await
        .expect("schedules.list");
    let sid = schedules.last().unwrap()["id"].as_str().unwrap().to_string();
    for dow in 0..=4 {
        // 0=lunes .. 4=viernes
        rt.execute_command(
            "appointments.timeslots.create",
            &params(json!({
                "schedule_id": sid, "day_of_week": dow,
                "start_time": "09:00", "end_time": "18:00"
            })),
            ctx,
        )
        .await
        .expect("timeslots.create");
    }
}

/// Inserta una cita "viva" de un profesional vía el command público de create (handler WASM
/// si está compilado) o, si el .wasm no está, directamente con el sub-command SQL para no
/// depender del guest. Devuelve sin asumir el número de cita.
async fn book(rt: &Runtime, ctx: &RequestContext, staff_id: &str, start: &str, dur: i64) {
    // El handler WASM calcula end = start+dur; aquí lo precomputamos para el insert directo.
    let wasm = mdir("appointments").join("dist/handler.wasm").exists();
    if wasm {
        rt.execute_command(
            "appointments.appointments.create",
            &params(json!({
                "customer_name": "Cliente", "staff_id": staff_id, "staff_name": staff_id,
                "service_name": "Peinado/Lavado", "start_datetime": start, "duration_minutes": dur
            })),
            ctx,
        )
        .await
        .expect("appointments.create (WASM)");
    } else {
        // Sin guest compilado: insertamos la fila por el sub-command SQL (misma forma que
        // produce el handler). El motor de disponibilidad solo lee la tabla, así basta.
        let end = (chrono::DateTime::parse_from_rfc3339(start).unwrap()
            + Duration::minutes(dur))
        .to_rfc3339();
        // `execute_command_internal`: los sub-commands `_` son INTERNOS (hub#131/#145) y la puerta
        // pública (`execute_command`) los rechaza; aquí el test actúa como host embebedor
        // sembrando la intención exacta que el handler emitiría.
        rt.execute_command_internal(
            "appointments._bump_counter",
            &params(json!({ "day": "20990101" })),
            ctx,
        )
        .await
        .ok();
        rt.execute_command_internal(
            "appointments._insert_appointment",
            &params(json!({
                "appointment_id": null, "day": "20990101",
                "customer_id": null, "customer_name": "Cliente",
                "customer_phone": "", "customer_email": "",
                "staff_id": staff_id, "staff_name": staff_id,
                "service_id": null, "service_name": "Peinado/Lavado", "service_price": 0,
                "start_datetime": start, "end_datetime": end, "duration_minutes": dur,
                "status": "pending", "notes": "", "internal_notes": "", "booked_online": 0
            })),
            ctx,
        )
        .await
        .expect("_insert_appointment (SQL directo)");
    }
}

#[tokio::test]
async fn install_registers_availability_engine() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !wasm_present() {
        eprintln!("⚠ sin handler.wasm (appointments) — saltado");
        return;
    }
    let rt = rt_appts().await;
    let reg = rt.registry();
    assert!(reg.is_installed("appointments"));
    assert!(reg.get_query("appointments.availability.check").is_some());
    assert!(reg.get_command("appointments.appointments.create").is_some());
    assert!(reg.get_command("appointments.appointments.reschedule").is_some());
}

#[tokio::test]
async fn overlap_same_staff_rejected_distinct_staff_ok() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !wasm_present() {
        eprintln!("⚠ sin handler.wasm (appointments) — saltado");
        return;
    }
    let rt = rt_appts().await;
    let ctx = admin();
    set_overlap(&rt, &ctx, false).await; // OFF: solo si la profesional está libre
    let day = next_wednesday();
    let p1_start = format!("{day}T12:00:00+00:00");
    let dur = 30; // peinado/lavado

    // Peluquera1 @ 12:00 (30 min) → P1 ocupada 12:00–12:30.
    book(&rt, &ctx, "P1", &p1_start, dur).await;

    // 2ª cita de P1 dentro de la ventana → RECHAZADA por solape.
    let inside = format!("{day}T12:15:00+00:00");
    let (avail_p1, reason_p1) = check(&rt, &ctx, &inside, dur, Some("P1")).await;
    assert_eq!(avail_p1, 0, "2ª cita de P1 en su ventana debe rechazarse");
    assert_eq!(reason_p1, "overlap", "el motivo debe ser solape");

    // Misma franja exacta de P1 también solapa.
    let (avail_p1_exact, _) = check(&rt, &ctx, &p1_start, dur, Some("P1")).await;
    assert_eq!(avail_p1_exact, 0, "misma hora exacta de P1 también solapa");

    // Peluquera2 @ 12:00 → ACEPTADA (capacidad = nº de empleados, comprobado por staff_id).
    let (avail_p2, reason_p2) = check(&rt, &ctx, &p1_start, dur, Some("P2")).await;
    assert_eq!(avail_p2, 1, "P2 a la misma hora debe aceptarse (otra profesional)");
    assert_eq!(reason_p2, "", "P2 no tiene motivo de rechazo");

    // Después de la ventana de P1 (12:30) P1 vuelve a estar libre.
    let after = format!("{day}T12:30:00+00:00");
    let (avail_after, _) = check(&rt, &ctx, &after, dur, Some("P1")).await;
    assert_eq!(avail_after, 1, "a las 12:30 P1 ya está libre (ventana [12:00,12:30) cerrada)");
}

#[tokio::test]
async fn toggle_allow_overlapping_permits_double_booking() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !wasm_present() {
        eprintln!("⚠ sin handler.wasm (appointments) — saltado");
        return;
    }
    let rt = rt_appts().await;
    let ctx = admin();
    set_overlap(&rt, &ctx, true).await; // ON: permite varias citas a la misma hora
    let day = next_wednesday();
    let start = format!("{day}T12:00:00+00:00");
    let dur = 30;

    book(&rt, &ctx, "P1", &start, dur).await;

    // Con el toggle ON, una 2ª cita de P1 a la misma hora se ACEPTA (no se comprueba solape).
    let (avail, reason) = check(&rt, &ctx, &start, dur, Some("P1")).await;
    assert_eq!(avail, 1, "con allow_overlapping=true la doble reserva se permite");
    assert_eq!(reason, "", "sin motivo de rechazo cuando el solape está permitido");
}

#[tokio::test]
async fn outside_working_schedule_rejected() {
    if !erplora_runtime::require_modules_workspace() {
        return;
    }
    if !wasm_present() {
        eprintln!("⚠ sin handler.wasm (appointments) — saltado");
        return;
    }
    let rt = rt_appts().await;
    let ctx = admin();
    set_overlap(&rt, &ctx, false).await;
    seed_weekday_schedule(&rt, &ctx).await; // lun–vie 09:00–18:00
    let day = next_wednesday(); // miércoles → día laborable

    // Dentro del horario (12:00) y sin citas → DISPONIBLE.
    let within = format!("{day}T12:00:00+00:00");
    let (avail_in, _) = check(&rt, &ctx, &within, 30, Some("P1")).await;
    assert_eq!(avail_in, 1, "12:00 de un miércoles está dentro del horario");

    // Fuera del horario (08:00, antes de abrir) → RECHAZADA por fuera de horario.
    let before = format!("{day}T08:00:00+00:00");
    let (avail_out, reason_out) = check(&rt, &ctx, &before, 30, Some("P1")).await;
    assert_eq!(avail_out, 0, "08:00 está fuera del horario de trabajo");
    assert_eq!(reason_out, "outside_schedule", "el motivo debe ser fuera de horario");
}

/// Reproducción directa de hub#110 (P0): el command público `appointments.appointments.create`
/// debe RECHAZAR una 2ª cita solapada para la MISMA profesional cuando `allow_overlapping=false`
/// (no basta con que `availability.check` lo detecte — el create mismo lo impide), Y
/// `appointments.appointments.list` debe seguir funcionando justo después de crear una cita
/// (antes rompía con SQLITE_MISMATCH code 20 por `NULL = ''` en el filtro opcional).
///
/// Antes del fix el create aceptaba el solape porque su handler WASM no recibía las citas
/// existentes (no declaraba `reads`); y el list cascaba por el bind NULL del filtro opcional.
#[tokio::test]
async fn create_rejects_overlap_and_list_works_after_creation() {
    if !wasm_present() {
        eprintln!("SKIP: modules-workspace not present (CI)");
        return;
    }
    let rt = rt_appts().await;
    let ctx = admin();
    set_overlap(&rt, &ctx, false).await; // allow_overlapping=false
    let day = next_wednesday();
    let start = format!("{day}T12:00:00+00:00");
    let dur = 30;

    // 1ª cita de P1 @ 12:00 → debe crearse OK.
    rt.execute_command(
        "appointments.appointments.create",
        &params(json!({
            "customer_name": "Cliente 1", "staff_id": "P1", "staff_name": "P1",
            "service_name": "Peinado/Lavado", "start_datetime": start, "duration_minutes": dur
        })),
        &ctx,
    )
    .await
    .expect("1ª cita debe crearse");

    // Bug (b) de #110: appointments.list justo después de crear. Pasamos solo day_start/day_end
    // y limit, OMITIENDO status/staff_id (el runtime los inyecta como NULL → antes SQLITE_MISMATCH).
    let day_start = format!("{day}T00:00:00+00:00");
    let day_end = format!("{day}T23:59:59+00:00");
    let rows = rt
        .execute_query(
            "appointments.appointments.list",
            &params(json!({ "day_start": day_start, "day_end": day_end, "limit": 100 })),
            &ctx,
        )
        .await
        .expect("appointments.list no debe romper tras crear (hub#110)");
    assert_eq!(rows.len(), 1, "tras 1 cita creada, el listado debe devolver 1 fila");
    assert_eq!(rows[0]["staff_name"].as_str(), Some("P1"));

    // Bug (a) de #110: 2ª cita SOLAPADA (12:15, misma P1) → el command create debe RECHAZARLA.
    // El runtime precarga `appointments.appointments.conflicting` (reads) y el handler lo detecta.
    let overlap_start = format!("{day}T12:15:00+00:00");
    let err = rt
        .execute_command(
            "appointments.appointments.create",
            &params(json!({
                "customer_name": "Cliente 2", "staff_id": "P1", "staff_name": "P1",
                "service_name": "Peinado/Lavado", "start_datetime": overlap_start,
                "duration_minutes": dur
            })),
            &ctx,
        )
        .await
        .expect_err("2ª cita solapada del mismo staff debe rechazarse (hub#110)");
    let msg = err.to_string();
    assert!(
        msg.contains("overlap"),
        "el rechazo debe ser por solape, no otro error. llegó: {msg}"
    );

    // El listado sigue intacto (la cita rechazada no se materializó).
    let rows_after = rt
        .execute_query(
            "appointments.appointments.list",
            &params(json!({ "day_start": day_start, "day_end": day_end, "limit": 100 })),
            &ctx,
        )
        .await
        .expect("appointments.list sigue funcionando");
    assert_eq!(
        rows_after.len(),
        1,
        "la cita solapada rechazada no debe aparecer en el listado"
    );
}
