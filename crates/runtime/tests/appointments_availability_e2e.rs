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
use erplora_db::{testutil::fresh_db, Params};
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
    let mut rt = Runtime::with_hub_id(Box::new(db), "h1");
    // appointments `depends_on` customers + services + staff (FK lógicas cross-módulo; staff por
    // ADR-0074, selector de profesional) y services `depends_on` taxes (ADR-0066); el installer
    // valida la cadena, así que las instalamos en orden topológico primero (staff no depende de nada).
    rt.install_from_dir(&mdir("taxes"))
        .await
        .expect("instalar taxes");
    rt.install_from_dir(&mdir("customers"))
        .await
        .expect("instalar customers");
    rt.install_from_dir(&mdir("services"))
        .await
        .expect("instalar services");
    rt.install_from_dir(&mdir("staff"))
        .await
        .expect("instalar staff");
    // appointments 1.1.57 added `depends_on: schedules >= 2.0.17` (the working-hours engine it
    // asserts against in scenario 4); schedules itself depends on nothing.
    rt.install_from_dir(&mdir("schedules"))
        .await
        .expect("instalar schedules");
    rt.install_from_dir(&mdir("appointments"))
        .await
        .expect("instalar appointments");
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
    (
        row["available"].as_i64().unwrap_or(-1),
        row["reason"].as_str().unwrap_or("?").to_string(),
    )
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

/// The links a booking needs, created for real (hub#1053).
///
/// `appointments` stopped believing the browser: `create` RESOLVES customer, service and staff
/// against the hub and refuses what it cannot find (appointments#11, handler `4ceed7e`). This
/// test used to send `cust-1`/`svc-1`/`P1` — three ids nobody ever created — and passed only
/// because the handler took the payload's word for it. That was the very bug appointments#11
/// closed, so the module is right and the fixture was the thing left behind.
///
/// The tax key is READ from `taxes` rather than hardcoded: a seed that renames its categories
/// should not silently turn this into a red test about something else.
struct Links {
    customer_id: String,
    service_id: String,
    staff_id: String,
    /// A second bookable professional: "the other one is free at that hour" is only a real
    /// assertion if that professional exists.
    other_staff_id: String,
}

/// The id of the row whose `field` equals `value`. Never `.last()`: these list queries are
/// ordered by the module (alphabetically, in `staff`'s case), so "the one I just created" and
/// "the last row" are different rows — and the test that trusted them agreed only by luck.
fn id_where(rows: &[serde_json::Value], field: &str, value: &str) -> String {
    rows.iter()
        .find(|r| r[field].as_str() == Some(value))
        .unwrap_or_else(|| panic!("no row with {field}={value:?} — got {rows:?}"))["id"]
        .as_str()
        .expect("id")
        .to_string()
}

async fn seed_links(rt: &Runtime, ctx: &RequestContext) -> Links {
    let categories = rt
        .execute_query("taxes.categories.list", &Params::new(), ctx)
        .await
        .expect("taxes.categories.list");
    let tax_key = categories
        .first()
        .and_then(|c| c["key"].as_str())
        .expect("taxes must seed at least one category")
        .to_string();

    rt.execute_command(
        "customers.create",
        &params(json!({ "name": "Cliente 1" })),
        ctx,
    )
    .await
    .expect("customers.create");
    let customer_id = id_where(
        &rt.execute_query("customers.list", &Params::new(), ctx)
            .await
            .expect("customers.list"),
        "name",
        "Cliente 1",
    );

    rt.execute_command(
        "services.services.create",
        &params(json!({
            "name": "Peinado/Lavado", "tax_category_key": tax_key,
            "duration_minutes": 30, "is_bookable": 1
        })),
        ctx,
    )
    .await
    .expect("services.services.create");
    let service_id = id_where(
        &rt.execute_query("services.services.list", &Params::new(), ctx)
            .await
            .expect("services.services.list"),
        "name",
        "Peinado/Lavado",
    );

    rt.execute_command(
        "staff.members.create",
        &params(json!({ "first_name": "Pro", "last_name": "Uno", "is_bookable": 1 })),
        ctx,
    )
    .await
    .expect("staff.members.create");
    let staff_id = id_where(
        &rt.execute_query("staff.members.list", &Params::new(), ctx)
            .await
            .expect("staff.members.list"),
        "last_name",
        "Uno",
    );

    rt.execute_command(
        "staff.members.create",
        &params(json!({ "first_name": "Pro", "last_name": "Dos", "is_bookable": 1 })),
        ctx,
    )
    .await
    .expect("staff.members.create (2)");
    let members = rt
        .execute_query("staff.members.list", &Params::new(), ctx)
        .await
        .expect("staff.members.list");
    let other_staff_id = id_where(&members, "last_name", "Dos");

    Links {
        customer_id,
        service_id,
        staff_id,
        other_staff_id,
    }
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
    let sid = schedules.last().unwrap()["id"]
        .as_str()
        .unwrap()
        .to_string();
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
async fn book(
    rt: &Runtime,
    ctx: &RequestContext,
    links: &Links,
    staff_id: &str,
    start: &str,
    dur: i64,
) {
    // El handler WASM calcula end = start+dur; aquí lo precomputamos para el insert directo.
    let wasm = mdir("appointments").join("dist/handler.wasm").exists();
    if wasm {
        rt.execute_command(
            "appointments.appointments.create",
            &params(json!({
                // La cita se reserva contra registros REALES (appointments#21): cliente, servicio
                // y profesional son ENLACES (`*_id`), y el nombre/precio denormalizado viaja CON
                // ellos como snapshot histórico. Un nombre suelto ya no se acepta.
                "customer_id": links.customer_id, "customer_name": "Cliente",
                "service_id": links.service_id, "service_name": "Peinado/Lavado",
                "staff_id": staff_id, "staff_name": staff_id,
                "start_datetime": start, "duration_minutes": dur
            })),
            ctx,
        )
        .await
        .expect("appointments.create (WASM)");
    } else {
        // Sin guest compilado: insertamos la fila por el sub-command SQL (misma forma que
        // produce el handler). El motor de disponibilidad solo lee la tabla, así basta.
        let end = (chrono::DateTime::parse_from_rfc3339(start).unwrap() + Duration::minutes(dur))
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
                "customer_id": links.customer_id, "customer_name": "Cliente",
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
    assert!(reg
        .get_command("appointments.appointments.create")
        .is_some());
    assert!(reg
        .get_command("appointments.appointments.reschedule")
        .is_some());
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
    let links = seed_links(&rt, &ctx).await;
    let p1 = links.staff_id.clone();
    let day = next_wednesday();
    let p1_start = format!("{day}T12:00:00+00:00");
    let dur = 30; // peinado/lavado

    // Peluquera1 @ 12:00 (30 min) → P1 ocupada 12:00–12:30.
    book(&rt, &ctx, &links, &p1, &p1_start, dur).await;

    // 2ª cita de P1 dentro de la ventana → RECHAZADA por solape.
    let inside = format!("{day}T12:15:00+00:00");
    let (avail_p1, reason_p1) = check(&rt, &ctx, &inside, dur, Some(&p1)).await;
    assert_eq!(avail_p1, 0, "2ª cita de P1 en su ventana debe rechazarse");
    assert_eq!(reason_p1, "overlap", "el motivo debe ser solape");

    // Misma franja exacta de P1 también solapa.
    let (avail_p1_exact, _) = check(&rt, &ctx, &p1_start, dur, Some(&p1)).await;
    assert_eq!(avail_p1_exact, 0, "misma hora exacta de P1 también solapa");

    // Peluquera2 @ 12:00 → ACEPTADA (capacidad = nº de empleados, comprobado por staff_id).
    let (avail_p2, reason_p2) = check(&rt, &ctx, &p1_start, dur, Some(&links.other_staff_id)).await;
    assert_eq!(
        avail_p2, 1,
        "P2 a la misma hora debe aceptarse (otra profesional)"
    );
    assert_eq!(reason_p2, "", "P2 no tiene motivo de rechazo");

    // Después de la ventana de P1 (12:30) P1 vuelve a estar libre.
    let after = format!("{day}T12:30:00+00:00");
    let (avail_after, _) = check(&rt, &ctx, &after, dur, Some(&p1)).await;
    assert_eq!(
        avail_after, 1,
        "a las 12:30 P1 ya está libre (ventana [12:00,12:30) cerrada)"
    );
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
    let links = seed_links(&rt, &ctx).await;
    let staff = links.staff_id.clone();
    let day = next_wednesday();
    let start = format!("{day}T12:00:00+00:00");
    let dur = 30;

    book(&rt, &ctx, &links, &staff, &start, dur).await;

    // Con el toggle ON, una 2ª cita de P1 a la misma hora se ACEPTA (no se comprueba solape).
    let (avail, reason) = check(&rt, &ctx, &start, dur, Some(&links.staff_id)).await;
    assert_eq!(
        avail, 1,
        "con allow_overlapping=true la doble reserva se permite"
    );
    assert_eq!(
        reason, "",
        "sin motivo de rechazo cuando el solape está permitido"
    );
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
    assert_eq!(
        reason_out, "outside_schedule",
        "el motivo debe ser fuera de horario"
    );
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
    let links = seed_links(&rt, &ctx).await;
    let day = next_wednesday();
    let start = format!("{day}T12:00:00+00:00");
    let dur = 30;

    // 1ª cita de P1 @ 12:00 → debe crearse OK.
    rt.execute_command(
        "appointments.appointments.create",
        &params(json!({
            // Alta ligada (appointments#21): customer_id/service_id/staff_id son obligatorios,
            // y desde appointments#11 se RESUELVEN contra el hub — han de existir de verdad.
            "customer_id": links.customer_id, "customer_name": "Cliente 1",
            "service_id": links.service_id, "service_name": "Peinado/Lavado",
            "staff_id": links.staff_id, "staff_name": "Pro Uno",
            "start_datetime": start, "duration_minutes": dur
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
    assert_eq!(
        rows.len(),
        1,
        "tras 1 cita creada, el listado debe devolver 1 fila"
    );
    assert_eq!(rows[0]["staff_name"].as_str(), Some("Pro Uno"));

    // Bug (a) de #110: 2ª cita SOLAPADA (12:15, misma P1) → el command create debe RECHAZARLA.
    // El runtime precarga `appointments.appointments.conflicting` (reads) y el handler lo detecta.
    let overlap_start = format!("{day}T12:15:00+00:00");
    let err = rt
        .execute_command(
            "appointments.appointments.create",
            &params(json!({
                // Enlaces REALES a propósito: con ids inventados el rechazo llegaría por
                // `customer_not_found` y este test daría por bueno el solape sin haberlo probado.
                "customer_id": links.customer_id, "customer_name": "Cliente 2",
                "service_id": links.service_id, "service_name": "Peinado/Lavado",
                "staff_id": links.staff_id, "staff_name": "Pro Uno",
                "start_datetime": overlap_start, "duration_minutes": dur
            })),
            &ctx,
        )
        .await
        .expect_err("2ª cita solapada del mismo staff debe rechazarse (hub#110)");
    // El rechazo se identifica por su CÓDIGO estable, no por el texto. `appointments` dejó de
    // devolver `Err("overlap: …")` y pasó a un `DomainError` con código
    // (`appointments.overlapping_appointment`, appointments#70/#71) precisamente para que nadie
    // tenga que olfatear un prefijo — y este e2e seguía olfateándolo, así que se rompía en cuanto
    // el módulo escribió el mensaje en lenguaje de negocio. El mensaje es texto humano y además
    // traducible (ADR-0055): afirmar sobre él es afirmar sobre la traducción.
    match &err {
        erplora_runtime::RuntimeError::Domain { code, .. } => assert_eq!(
            code, "appointments.overlapping_appointment",
            "el rechazo debe ser por solape, no otro error"
        ),
        other => panic!("se esperaba un rechazo de negocio por solape, llegó: {other:?}"),
    }

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
