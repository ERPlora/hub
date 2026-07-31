//! Capa SERVER del RESET del hub (ADR-0166).
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

use erplora_runtime::reset::{execute_reset, plan_reset, ResetSelection};

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
