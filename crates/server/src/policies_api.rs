//! **La puerta HTTP de las normas del dueño** (hub#1701, ADR-0476).
//!
//! ```text
//! GET/POST        /api/hub/policies              lista / crea
//! GET             /api/hub/policies/checkpoints  dónde se puede poner una norma
//! GET/PUT/DELETE  /api/hub/policies/{id}
//! ```
//!
//! **Core REST, no comandos `hub.*`** — mismo reparto que los flujos (`flows_api.rs`, ADR-0283 §9):
//! una norma no es el dato de un módulo, es la configuración del propio hub, y va en el mismo
//! estante que las keys, los usuarios o la dead-letter.
//!
//! **Puerta = la sesión local de una PERSONA owner/admin**, nunca una API key ni el token de
//! máquina. Una norma decide si una venta se puede cobrar; una credencial de integración copiable,
//! guardada en el `.env` de un tercero, no decide eso.
//!
//! 🔴 Y **sin capability de módulo**, a diferencia de `admin_session!` de los flujos: allí la
//! capability existe porque el SDK expone la superficie de flujos a los módulos, y sin ella
//! cualquier módulo instalado podría escribirse una automatización que corre comandos en nombre del
//! dueño. Aquí no hay superficie de SDK que abrir —las normas se escriben desde la pantalla del
//! hub— así que pedir una capability sería pedir permiso para una puerta que no existe.
//!
//! `created_by`/`updated_by` salen SIEMPRE de la sesión resuelta, jamás del body (misma regla que
//! `granted_by` en `flows_api.rs` y `discarded_by` en `outbox_admin.rs`).
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use erplora_runtime::policies::{self, NewPolicy};
use erplora_runtime::RuntimeError;
use serde_json::{json, Value};

use crate::auth;
use crate::state::AppState;

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

fn bad_request(code: &str, message: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

/// El status HTTP que significa un código `policy.*` — **por familia, no caso a caso** (misma regla
/// que [`crate::flows_api`], hub#734).
///
/// Toda negativa del núcleo viaja como `RuntimeError::Domain`, y `Domain` es `409` en el resto del
/// hub. Aquí eso sería falso casi siempre: `409` le dice al llamador «reintenta, el estado cambiará»
/// y ninguna de estas tres cosas cambia sola. La pantalla del dueño decide qué pintar mirando el
/// status **antes** de mirar el código, así que la distinción tiene que estar ahí:
///
/// - `…not_found` → **404**. No existe: ni la norma, ni el punto de control que dice gatear.
/// - `policy.outcome_not_available` → **501**. La consecuencia SÍ está en el vocabulario y este core
///   todavía no la sabe aplicar (`elevate:`, hub#1710). Es la única de la familia que se arregla
///   **esperando una release** en vez de corrigiendo la norma, y decirle `400` mandaría al dueño a
///   reescribir algo que ya está bien.
/// - el resto de `policy.` → **400**. Lo que el llamador mandó mal.
///
/// ⚠️ Un código que **no** empiece por `policy.` cae a [`crate::err_response`] sin tocar: el
/// `not_found` de un módulo no es el de este kernel, y la regla del sufijo lo reclamaría encantada.
/// Es la primera línea a propósito, antes de mirar ningún sufijo.
///
/// [`policies::ERR_BLOCKED`] no se mapea aquí y no es un olvido: una norma en vigor niega por
/// `/api/commands/…`, que es la superficie del dispatcher, no esta.
fn policy_status(code: &str) -> Option<StatusCode> {
    if !code.starts_with("policy.") {
        return None;
    }
    let status = match code {
        policies::ERR_OUTCOME_NOT_AVAILABLE => StatusCode::NOT_IMPLEMENTED,
        // `policy.not_found` lleva un `.` donde los demás llevan `_`, así que el sufijo se compara
        // sin él — y ningún código de la familia acaba en `not_found` significando otra cosa.
        _ if code.ends_with("not_found") => StatusCode::NOT_FOUND,
        _ => StatusCode::BAD_REQUEST,
    };
    Some(status)
}

/// Los errores del núcleo, con el status que [`policy_status`] dice que significan.
fn policy_err(e: RuntimeError) -> Response {
    if let RuntimeError::Domain { code, message } = &e {
        if let Some(status) = policy_status(code) {
            return (
                status,
                Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
            )
                .into_response();
        }
    }
    crate::err_response(e)
}

/// Resuelve la sesión de admin y devuelve el runtime más «quién está haciendo esto», ya en la forma
/// `hub_user:<id>` que guardan las columnas de auditoría.
///
/// Anónimo → `401`; cajero → `403`; API key → `401`/`403`, porque `require_admin_session` solo
/// mira la sesión local y una key no la trae.
macro_rules! admin_session {
    ($st:expr, $headers:expr) => {{
        let arc = match $st.runtime_for(&$st.hub_id()).await {
            Ok(arc) => arc,
            Err(e) => return crate::tenant_rejected(e),
        };
        let rt = arc.read().await;
        let admin = match auth::require_admin_session(&$headers, &$st.config, &rt).await {
            Ok(admin) => admin,
            Err(e) => return rejected(e),
        };
        let who = format!("hub_user:{}", admin.id);
        (arc.clone(), who)
    }};
}

/// Lee el body de un `POST`/`PUT`.
///
/// Un body al que le falte un campo —o que traiga `mode` como número— es un error del llamador, no
/// del dueño: sale como `400 invalid_payload` con el motivo de serde, que dice exactamente qué
/// campo falta. Los campos que la persona SÍ puede equivocarse escribiendo (el punto de control, la
/// condición, la consecuencia, el mensaje) los juzga `policies::validate`, con su código propio.
fn new_policy(body: &Value) -> Result<NewPolicy, Response> {
    serde_json::from_value::<NewPolicy>(body.clone())
        .map_err(|e| bad_request("invalid_payload", &e.to_string()))
}

/// `GET /api/hub/policies/checkpoints` — dónde puede el dueño poner una norma.
///
/// Sale del Registry, no de la BD: son los puntos de control que declaran los módulos **instalados
/// y activos** ahora mismo. Es la lista que la pantalla necesita para ofrecer sitios, y la misma
/// que decide si una norma guardada sigue aplicándose.
pub async fn list_checkpoints(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.read().await;
    Json(json!({ "ok": true, "data": rt.policy_checkpoints() })).into_response()
}

pub async fn list_policies(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.read().await;
    match rt.list_policies().await {
        Ok(policies) => Json(json!({ "ok": true, "data": policies })).into_response(),
        Err(e) => policy_err(e),
    }
}

pub async fn create_policy(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(body): Json<Value>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let new = match new_policy(&body) {
        Ok(new) => new,
        Err(response) => return response,
    };
    let rt = arc.read().await;
    match rt.create_policy(&new, &who).await {
        Ok(policy) => (
            StatusCode::CREATED,
            Json(json!({ "ok": true, "data": policy })),
        )
            .into_response(),
        Err(e) => policy_err(e),
    }
}

pub async fn get_policy(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let (arc, _) = admin_session!(st, headers);
    let rt = arc.read().await;
    match rt.get_policy(&id).await {
        Ok(policy) => Json(json!({ "ok": true, "data": policy })).into_response(),
        Err(e) => policy_err(e),
    }
}

/// `PUT /api/hub/policies/{id}` — la norma entera, no un parche: es la misma validación que el alta,
/// así que promover de `warn` a `enforce` pasa por el mismo aro que escribirla.
pub async fn update_policy(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    Json(body): Json<Value>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let new = match new_policy(&body) {
        Ok(new) => new,
        Err(response) => return response,
    };
    let rt = arc.read().await;
    match rt.update_policy(&id, &new, &who).await {
        Ok(policy) => Json(json!({ "ok": true, "data": policy })).into_response(),
        Err(e) => policy_err(e),
    }
}

/// `DELETE /api/hub/policies/{id}` — soft-delete: la fila sobrevive porque es el único registro de
/// que esta norma estuvo en vigor, y deja de aplicarse en el comando siguiente.
pub async fn delete_policy(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let (arc, who) = admin_session!(st, headers);
    let rt = arc.read().await;
    match rt.delete_policy(&id, &who).await {
        Ok(()) => {
            Json(json!({ "ok": true, "data": { "id": id, "deleted": true } })).into_response()
        }
        Err(e) => policy_err(e),
    }
}
