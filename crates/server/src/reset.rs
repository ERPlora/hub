//! Capa SERVER del RESET del hub (ADR-0170).
//!
//! El MOTOR vive en el runtime (`erplora_runtime::reset::{plan_reset, execute_reset}`); esta capa
//! solo añade lo que es del server: **auth** (sesión admin owner/admin — el mismo gate que
//! `PUT /api/settings`, el certificado y el export: es la operación más destructiva del producto
//! y no puede tener un gate más flojo), el `hub_id` del plano de DATOS, y el envelope JSON.
//!
//! Endpoints (montados en `crate::app`):
//!   POST /api/hub/reset/plan  → `{ ok, plan }`    dry-run: secciones + filas + bloqueos
//!   POST /api/hub/reset       → `{ ok, report }`  borra lo seleccionado, en una transacción
//!
//! El **límite fiscal** (facturas remitidas a la AEAT, RD 1007/2023) lo aplica el motor, no esta
//! capa: así vale igual para cualquier consumidor de la API, no solo para el panel del shell.

use axum::extract::State;
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Deserialize;
use serde_json::json;

use erplora_runtime::reset::{
    execute_reset, last_import_report_for_hub, list_import_batches, plan_reset, undo_import,
    ResetSelection,
};

use crate::auth;
use crate::state::AppState;

/// `401` para fallo de auth (sin sesión / sesión inválida / rol insuficiente).
fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

/// Error en el envelope estándar `{ ok:false, error:{ message } }`.
fn err(code: StatusCode, msg: &str) -> Response {
    (code, Json(json!({ "ok": false, "error": { "message": msg } }))).into_response()
}

/// Espejo serde de `ResetSelection` (que no deriva Deserialize). Todo por defecto en `false`:
/// un body incompleto NUNCA amplía lo que se borra.
#[derive(Deserialize, Default)]
pub struct ResetSelectionReq {
    #[serde(default)]
    settings: bool,
    #[serde(default)]
    users: bool,
    #[serde(default)]
    media: bool,
    #[serde(default)]
    fiscal: bool,
    /// The hub's role set (`hub_role_activation`, hub#417). `#[serde(default)]` like the rest: an
    /// older shell that does not send the field switches nothing off.
    #[serde(default)]
    roles: bool,
    /// The print queue (`_print_queue`, hub#502). `#[serde(default)]`: an older shell that does
    /// not send the field clears no queue — same forward-compat rule as every other section.
    #[serde(default)]
    print_queue: bool,
    #[serde(default)]
    modules: Vec<String>,
}

impl ResetSelectionReq {
    fn into_selection(self) -> ResetSelection {
        ResetSelection {
            settings: self.settings,
            users: self.users,
            media: self.media,
            fiscal: self.fiscal,
            roles: self.roles,
            print_queue: self.print_queue,
            modules: self.modules,
        }
    }
}

/// Body del reset. `selection` es obligatorio de facto: sin él no se borra nada.
#[derive(Deserialize)]
pub struct ResetReq {
    #[serde(default)]
    selection: ResetSelectionReq,
}

/// POST /api/hub/reset/plan — **dry-run**: qué secciones hay, cuántas filas se llevaría cada una
/// y cuáles están bloqueadas (con el motivo). No escribe nada.
///
/// Va detrás del gate admin igual que el reset: enumera el volumen de negocio del hub (cuántos
/// productos, clientes, ventas), que no es información pública.
pub async fn reset_plan(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    // hub del PLANO DE DATOS: el mismo contexto que usan /api/command|query (en Dev es el de
    // cabecera/`local`). Mismo criterio que el export, por el mismo motivo: si el plan mirase
    // `config.hub_id` mientras los datos van a otro, contaría cero y mentiría al usuario.
    let data_hub_id = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx.hub_id,
        Err(e) => return unauthorized(e),
    };

    match plan_reset(&rt, &data_hub_id).await {
        Ok(plan) => (StatusCode::OK, Json(json!({ "ok": true, "plan": plan }))).into_response(),
        Err(e) => err(
            StatusCode::INTERNAL_SERVER_ERROR,
            &format!("no se pudo calcular el plan: {e}"),
        ),
    }
}

/// POST /api/hub/reset — borra las secciones seleccionadas, en UNA transacción.
///
/// El usuario que ejecuta nunca se borra a sí mismo: su id sale de la **sesión admin**, no del
/// body (si viniera del cliente, cualquiera podría pedir que se conservase a otro y expulsarse).
pub async fn reset_hub(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<ResetReq>>,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(u) => u,
        Err(e) => return unauthorized(e),
    };
    let data_hub_id = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx.hub_id,
        Err(e) => return unauthorized(e),
    };
    let Some(Json(req)) = body else {
        return err(StatusCode::UNPROCESSABLE_ENTITY, "falta el body JSON { selection }");
    };

    match execute_reset(&rt, &data_hub_id, &req.selection.into_selection(), &admin.id).await {
        Ok(report) => {
            (StatusCode::OK, Json(json!({ "ok": true, "report": report }))).into_response()
        }
        // El motor rechaza aquí lo bloqueado por el límite fiscal: 409 (conflicto con el estado
        // del hub), no 500 — no es un fallo, es una regla. El mensaje ya explica el motivo legal.
        Err(e) => err(StatusCode::CONFLICT, &e.to_string()),
    }
}

// ── Lotes de importación: listar y deshacer (ADR-0170) ──────────────────────────────────

/// Body de `POST /api/hub/import/undo`.
#[derive(Deserialize)]
pub struct UndoReq {
    batch_id: String,
}

/// GET /api/hub/import/batches — importaciones del hub, de la más reciente a la más antigua.
///
/// Alimenta el panel «deshacer esta importación». Va tras el gate admin: enumera qué blueprints
/// se han cargado y cuántas filas trajo cada uno.
pub async fn import_batches(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let data_hub_id = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx.hub_id,
        Err(e) => return unauthorized(e),
    };
    match list_import_batches(&rt, &data_hub_id).await {
        Ok(batches) => {
            (StatusCode::OK, Json(json!({ "ok": true, "batches": batches }))).into_response()
        }
        Err(e) => err(
            StatusCode::INTERNAL_SERVER_ERROR,
            &format!("no se pudieron listar las importaciones: {e}"),
        ),
    }
}

/// GET /api/hub/import/report — recovers the LAST actionable import report for the hub (hub#763).
///
/// The Dashboard hero points an admin at «Settings › Data» after a partial import, and that screen
/// used to start at the catalogue no matter what — the report was gone the moment navigation
/// dropped the in-memory `ref`. This endpoint hands the Data tab the persisted report (most recent
/// first): the extended document the server stored (sections + installed_modules + media + fiscal),
/// its `batch_id` (to undo or retry), its blueprint name and when it ran. Behind the same admin
/// gate as the rest of the import surface.
///
/// `None` (a `{ ok: true, report: null }` body) is the honest answer for a hub that never ran an
/// import, or whose last batch was undone (its report row is deleted with the batch): the Data tab
/// shows the catalogue, exactly as before.
pub async fn import_report(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let data_hub_id = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx.hub_id,
        Err(e) => return unauthorized(e),
    };
    match last_import_report_for_hub(&rt, &data_hub_id).await {
        Ok(None) => (StatusCode::OK, Json(json!({ "ok": true, "report": null }))).into_response(),
        Ok(Some(stored)) => {
            // `stored.report` is opaque JSON the writer put there (runtime report, or the server's
            // extended one). Parse it back so the body is a structured object, not a nested string.
            let parsed = serde_json::from_str::<serde_json::Value>(&stored.report)
                .unwrap_or_else(|_| json!({ "sections": [] }));
            (
                StatusCode::OK,
                Json(json!({
                    "ok": true,
                    "report": {
                        "batch_id": stored.batch_id,
                        "name": stored.name,
                        "created_at": stored.created_at,
                        "report": parsed,
                    }
                })),
            )
                .into_response()
        }
        Err(e) => err(
            StatusCode::INTERNAL_SERVER_ERROR,
            &format!("no se pudo leer el último informe de importación: {e}"),
        ),
    }
}

/// POST /api/hub/import/undo — deshace una importación: borra EXACTAMENTE las filas que trajo,
/// sin tocar lo que el usuario haya creado después.
///
/// Un lote desconocido (o de otro hub) es un **no-op 200**, no un error: el usuario puede pulsar
/// dos veces o reintentar tras una red mala, y eso no debe parecer un fallo.
pub async fn undo_import_batch(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<UndoReq>>,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(rt) => rt,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let data_hub_id = match auth::authenticate(&headers, &st.config, &rt).await {
        Ok(ctx) => ctx.hub_id,
        Err(e) => return unauthorized(e),
    };
    let Some(Json(req)) = body else {
        return err(StatusCode::UNPROCESSABLE_ENTITY, "falta el body JSON { batch_id }");
    };
    if req.batch_id.trim().is_empty() {
        return err(StatusCode::UNPROCESSABLE_ENTITY, "batch_id vacío");
    }

    match undo_import(&rt, &data_hub_id, req.batch_id.trim()).await {
        Ok(report) => {
            (StatusCode::OK, Json(json!({ "ok": true, "report": report }))).into_response()
        }
        Err(e) => err(StatusCode::INTERNAL_SERVER_ERROR, &e.to_string()),
    }
}
