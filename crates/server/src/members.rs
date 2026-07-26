//! ADR-0157 §7 — **provisioning bidireccional de miembros** vía la API del SaaS.
//!
//! El SaaS es la **fuente de verdad del ACCESO** (identidad + membresía `(usuario → org/hub)`); el
//! Hub no mantiene su propia lista de «quién puede entrar»: la administra vía API. Cuando un admin
//! del hub da de **alta** o **baja** a un usuario local, el runtime **notifica** al SaaS con la
//! credencial de **máquina** (`X-Hub-Token`) — el día a día del POS es sesión local/PIN, así que
//! casi nunca hay un JWT del SaaS fresco: el hub se autentica **a sí mismo**.
//!
//!  - **Alta:** `POST /api/v1/hub/device/members/` con `{email, role}` → el SaaS crea/enlaza la
//!    identidad **por email** + una membresía (pending) + la **invitación**.
//!  - **Baja:** `DELETE /api/v1/hub/device/members/{email}/` → revoca la membresía (el usuario sigue
//!    autenticándose en el SaaS, pero este hub/org **desaparece de su payload**). La *simetría*
//!    alta/baja es obligatoria: el deprovisioning es el fallo típico del invitation flow.
//!
//! El [`cloud_client::CloudClient`] construye la petición (URL/headers) y este módulo la **ejecuta**
//! con `reqwest` + el token de máquina **vivo** del [`AppState`] (mismo patrón que los proxies del
//! marketplace/entitlement). El secreto de máquina NO viaja al navegador: esto corre server-side.
//!
//! **Flujo admin de gestión de usuarios-login** (ADR-0157, checklist de core #2). Los handlers
//! `add_member`/`remove_member`/`list_members` exponen el alta/baja/listado de usuarios-login del
//! Hub a un **owner/admin** (gate `require_admin_session`). Cada alta/baja hace **dos** cosas: (1)
//! crea/desactiva el `hub_user` **local** (identidad, `identity::{create_login_user,
//! deactivate_login_user}`) y (2) **notifica al SaaS** (`notify_member_added/removed`, que es la
//! fuente de verdad del ACCESO). Es identidad (quién puede ENTRAR), **no** el módulo `staff.*`
//! (negocio). El orden es local→SaaS: si el SaaS falla, el alta local persiste (idempotente por
//! email) y el admin reintenta; devolvemos un status honesto para que lo sepa.

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde::Deserialize;
use serde_json::json;

use crate::auth;
use crate::state::AppState;

/// Body del **alta** (`POST members/`): identifica al usuario por **email** + su **rol Hub**. El rol
/// es el rol LOCAL/operativo del Hub (ortogonal al rol SaaS, ADR-0157 §6); el SaaS lo guarda con la
/// membresía para reflejarlo en el payload del usuario.
pub fn member_add_body(email: &str, role: &str) -> serde_json::Value {
    serde_json::json!({ "email": email, "role": role })
}

/// Fallo al notificar un alta/baja de miembro al SaaS.
#[derive(Debug)]
pub enum MembersError {
    /// El hub no está enrolado (sin `X-Hub-Token`): no puede administrar el acceso en el SaaS. Es un
    /// error de configuración/estado (bootstrap incompleto), no un fallo transitorio.
    NoMachineToken,
    /// Fallo de red/transporte al hablar con el SaaS.
    Transport(String),
    /// El SaaS respondió con un status **no-2xx** (`status`, cuerpo de respuesta).
    Cloud(u16, String),
}

impl std::fmt::Display for MembersError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            MembersError::NoMachineToken => {
                write!(f, "el hub no tiene credencial de máquina (X-Hub-Token)")
            }
            MembersError::Transport(e) => write!(f, "error de red hablando con el SaaS: {e}"),
            MembersError::Cloud(status, body) => write!(f, "el SaaS respondió {status}: {body}"),
        }
    }
}

impl std::error::Error for MembersError {}

/// Ejecuta una `PreparedRequest` (POST/DELETE) del `cloud-client` con `reqwest` + el body opcional.
/// Éxito solo con status 2xx; cualquier otro es [`MembersError::Cloud`].
async fn send(
    st: &AppState,
    prepared: cloud_client::PreparedRequest,
    body: Option<serde_json::Value>,
) -> Result<(), MembersError> {
    let mut req = match prepared.method {
        "POST" => st.http.post(&prepared.url),
        "DELETE" => st.http.delete(&prepared.url),
        other => {
            return Err(MembersError::Transport(format!(
                "método no soportado: {other}"
            )))
        }
    };
    for (name, value) in prepared.headers {
        req = req.header(name, value);
    }
    if let Some(body) = body {
        req = req.json(&body);
    }
    let resp = req
        .send()
        .await
        .map_err(|e| MembersError::Transport(e.to_string()))?;
    let status = resp.status().as_u16();
    if !(200..300).contains(&status) {
        let text = resp.text().await.unwrap_or_default();
        return Err(MembersError::Cloud(status, text));
    }
    Ok(())
}

/// **Alta:** notifica al SaaS que un admin ha dado de alta a `email` con el rol Hub `role`
/// (`POST /api/v1/hub/device/members/`). Requiere que el hub esté enrolado (token de máquina).
pub async fn notify_member_added(
    st: &AppState,
    email: &str,
    role: &str,
) -> Result<(), MembersError> {
    let auth = crate::auth::machine_auth(st).ok_or(MembersError::NoMachineToken)?;
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    send(
        st,
        cloud.members_add(&auth),
        Some(member_add_body(email, role)),
    )
    .await
}

/// **Baja:** notifica al SaaS que se revoca la membresía de `email`
/// (`DELETE /api/v1/hub/device/members/{email}/`). Contrapartida obligatoria del alta (simetría).
pub async fn notify_member_removed(st: &AppState, email: &str) -> Result<(), MembersError> {
    let auth = crate::auth::machine_auth(st).ok_or(MembersError::NoMachineToken)?;
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    send(st, cloud.members_remove(&auth, email), None).await
}

// ── Handlers HTTP del panel admin (ADR-0157 checklist core #2) ────────────────────────────────

/// Body del alta admin (`POST /api/members`): email del usuario-login + su **rol Hub** (local).
#[derive(Deserialize)]
pub struct AddMemberReq {
    pub email: String,
    pub role: String,
}

/// Mapea un [`MembersError`] a la respuesta HTTP del handler admin. El alta/baja **local** ya se
/// aplicó (idempotente); esto reporta que la parte SaaS falló, con un status honesto.
fn members_error_response(e: MembersError) -> Response {
    let (code, kind) = match &e {
        // Bootstrap incompleto: el hub no está enrolado → no puede administrar el acceso en el SaaS.
        MembersError::NoMachineToken => (StatusCode::CONFLICT, "not_enrolled"),
        MembersError::Transport(_) => (StatusCode::BAD_GATEWAY, "cloud_unreachable"),
        // Reenvía un 4xx del SaaS como 4xx (p. ej. email ya invitado); cualquier otro → 502.
        MembersError::Cloud(status, _) => (
            StatusCode::from_u16(*status)
                .ok()
                .filter(StatusCode::is_client_error)
                .unwrap_or(StatusCode::BAD_GATEWAY),
            "cloud_rejected",
        ),
    };
    (
        code,
        Json(json!({ "ok": false, "code": kind, "error": e.to_string() })),
    )
        .into_response()
}

/// `POST /api/members` — **alta** de un usuario-login (email + rol). Gate **owner/admin**
/// (`require_admin_session`). Crea/reactiva el `hub_user` local Y notifica el alta al SaaS. Es
/// identidad, NO `staff.*`. → `{ok, user}` (403 sin rol admin; 400 body inválido; 4xx/5xx si el
/// SaaS rechaza/no responde — el alta local ya se aplicó, idempotente por email).
pub async fn add_member(
    State(st): State<AppState>,
    headers: axum::http::HeaderMap,
    Json(req): Json<AddMemberReq>,
) -> Response {
    let email = req.email.trim().to_string();
    let role = req.role.trim().to_string();
    if email.is_empty() || role.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": "email y role son obligatorios" })),
        )
            .into_response();
    }
    // Gate admin + alta local bajo el MISMO lock; se suelta ANTES de la I/O de red al SaaS.
    let user = {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return crate::unauthorized(e);
        }
        match rt.create_login_user(&email, &role).await {
            Ok(user) => user,
            Err(e) => return crate::err_response(e),
        }
    };
    // Notifica el alta al SaaS (fuente de verdad del acceso). Si falla, el alta local persiste.
    if let Err(e) = notify_member_added(&st, &email, &role).await {
        return members_error_response(e);
    }
    Json(json!({ "ok": true, "user": user })).into_response()
}

/// `DELETE /api/members/:email` — **baja** de un usuario-login. Gate **owner/admin**. Desactiva el
/// `hub_user` local (una sesión abierta deja de resolver) Y revoca la membresía en el SaaS
/// (simetría del alta). → `{ok}` (403 sin rol admin; 4xx/5xx si el SaaS rechaza/no responde).
pub async fn remove_member(
    State(st): State<AppState>,
    headers: axum::http::HeaderMap,
    Path(email): Path<String>,
) -> Response {
    let email = email.trim().to_string();
    let existed = {
        let rt = st.runtime.lock().await;
        if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
            return crate::unauthorized(e);
        }
        match rt.deactivate_login_user(&email).await {
            Ok(existed) => existed,
            Err(e) => return crate::err_response(e),
        }
    };
    if let Err(e) = notify_member_removed(&st, &email).await {
        return members_error_response(e);
    }
    Json(json!({ "ok": true, "deactivated": existed })).into_response()
}

/// `GET /api/members` — lista los usuarios-login del hub para el panel admin. Gate **owner/admin**.
pub async fn list_members(
    State(st): State<AppState>,
    headers: axum::http::HeaderMap,
) -> Response {
    let rt = st.runtime.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return crate::unauthorized(e);
    }
    match rt.list_login_users().await {
        Ok(users) => Json(json!({ "ok": true, "members": users })).into_response(),
        Err(e) => crate::err_response(e),
    }
}
