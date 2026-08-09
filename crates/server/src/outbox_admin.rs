//! **Dead-letter operable** del outbox de eventos (hub#660 — ADR-0127 fase 2, ADR-0283 K6a):
//! `GET /api/hub/events/dead` · `POST /api/hub/events/{id}/retry` · `POST /api/hub/events/{id}/discard`.
//!
//! `_event_outbox.status='dead'` era TERMINAL. Tras `MAX_ATTEMPTS` la fila dejaba de moverse y la
//! única ventana era `GET /api/system` (`collect_logs`): 50 filas, sin payload y sin nada que
//! pulsar. Un evento que moría por una causa **arreglable** —un módulo desactivado a media entrega,
//! un listener roto— era trabajo perdido que nadie podía ver, reintentar ni cerrar. El caso que
//! motivó esto (un empleado cierra una venta → `verifactu.records.ingest_invoice` exige un permiso
//! que el emisor no lleva → 8 intentos → muerta, con la factura sin registrar) ya no ocurre: desde
//! hub#686 un listener corre con la autoridad de SU módulo, no con el rol del cajero. Esta
//! superficie sigue siendo el rescate de todo lo demás.
//!
//! Tres gestos, deliberadamente pequeños: **ver** qué murió (con el payload, que es lo que permite
//! distinguir una factura perdida de ruido), **reintentar** una fila devolviéndola al relay, y
//! **descartarla** para siempre. `discard` NUNCA borra: la fila es la única prueba de que el evento
//! existió, y descartarla es una decisión de alguien — las dos tienen que sobrevivir.
//!
//! **Auth = sesión local de un humano owner/admin** (patrón `api_keys.rs`, ADR-0057 §6), nunca una
//! API key ni el token de máquina. Reintentar re-ejecuta el command de otro con los permisos del
//! emisor, y descartar cierra un registro fiscal para siempre; ninguna de las dos es una gestión
//! que le toque a un token de integración — la key solo habla `/api/v1` (`auth::authenticate`).
//! `discarded_by` sale SIEMPRE de la sesión resuelta, jamás del cuerpo de la petición.
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;

use crate::auth;
use crate::state::AppState;

/// Cuántas dead-letters devuelve el listado. El tope duro lo pone el runtime (`MAX_DEAD_PAGE`).
const DEAD_PAGE: i64 = 100;

/// `401` si falta/ no vale la sesión; `403` si la sesión es válida pero el rol no administra el
/// Hub. La distinción importa: a un cajero volver a autenticarse no le va a servir de nada.
fn rejected(e: auth::AuthError) -> Response {
    let (status, code) = if e.is_forbidden() {
        (StatusCode::FORBIDDEN, "forbidden")
    } else {
        (StatusCode::UNAUTHORIZED, "unauthorized")
    };
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": e.message() } })),
    )
        .into_response()
}

/// `404` cuando el id no es una dead-letter **de este hub**: no existe, ya se entregó, ya se
/// descartó o es de otro tenant. Nunca un `200` silencioso que haga creer que se reintentó algo.
fn not_a_dead_letter() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(json!({
            "ok": false,
            "error": { "code": "not_found", "message": "no hay ninguna dead-letter con ese id" }
        })),
    )
        .into_response()
}

/// GET /api/hub/events/dead — la cola de dead-letters con su payload, `last_error` y `attempts`.
/// Auth = sesión admin.
pub async fn list_dead(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(arc) => arc,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return rejected(e);
    }
    match rt.list_dead_events(DEAD_PAGE).await {
        Ok(events) => Json(json!({ "ok": true, "data": events })).into_response(),
        Err(e) => crate::err_response(e),
    }
}

/// POST /api/hub/events/{id}/retry — devuelve la dead-letter al relay (`pending`, `attempts=0`,
/// vencida ya). La entrega la hace el relay en su siguiente ciclo, no este handler: el contrato
/// at-least-once + la idempotencia por `_event_delivery` siguen mandando, así que los listeners
/// que YA se entregaron en un intento anterior no se re-ejecutan. Auth = sesión admin.
pub async fn retry_dead(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(arc) => arc,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return rejected(e);
    }
    match rt.retry_dead_event(&id).await {
        Ok(true) => {
            Json(json!({ "ok": true, "data": { "id": id, "status": "pending" } })).into_response()
        }
        Ok(false) => not_a_dead_letter(),
        Err(e) => crate::err_response(e),
    }
}

/// POST /api/hub/events/{id}/discard — cierra la dead-letter: estado `discarded` + `discarded_at`
/// y `discarded_by`. **La fila se conserva** (auditable, nunca `DELETE`) y el relay no vuelve a
/// cogerla (`claim_next_due` solo reclama `pending`). Auth = sesión admin.
pub async fn discard_dead(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let arc = match st.runtime_for(&st.hub_id()).await {
        Ok(arc) => arc,
        Err(e) => return crate::tenant_rejected(e),
    };
    let rt = arc.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(user) => user,
        Err(e) => return rejected(e),
    };
    // Auditoría: quién lo descartó sale de la SESIÓN resuelta, nunca del cuerpo (mismo criterio
    // que el `created_by` de las API keys).
    let discarded_by = format!("hub_user:{}", admin.id);
    match rt.discard_dead_event(&id, &discarded_by).await {
        Ok(true) => Json(json!({
            "ok": true,
            "data": { "id": id, "status": erplora_runtime::outbox::STATUS_DISCARDED, "discarded_by": discarded_by }
        }))
        .into_response(),
        Ok(false) => not_a_dead_letter(),
        Err(e) => crate::err_response(e),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// El contrato HTTP completo vive en `tests/outbox_admin_test.rs` (router atado, sesiones
    /// reales, Postgres efímero). Aquí solo se fija la traducción de error → status, que es la
    /// pieza que distingue «no te has identificado» de «tú no puedes», y que ningún test de
    /// integración puede afirmar sin montar el hub entero.
    #[test]
    fn an_insufficient_role_is_forbidden_and_a_missing_session_is_unauthorized() {
        assert_eq!(
            rejected(auth::AuthError::Forbidden("rol cashier".into())).status(),
            StatusCode::FORBIDDEN
        );
        assert_eq!(
            rejected(auth::AuthError::MissingSession).status(),
            StatusCode::UNAUTHORIZED
        );
        assert_eq!(
            rejected(auth::AuthError::Invalid("sesión caducada".into())).status(),
            StatusCode::UNAUTHORIZED
        );
    }
}
