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
use crate::cloud_proxy;
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

/// El SaaS no acepta el alta/baja por una razón de NEGOCIO (email ya invitado, rol que no puede
/// conceder…). Lo que toca es corregir lo que se escribió y volver a guardar.
pub const CLOUD_REJECTED: &str = "cloud_rejected";
/// El SaaS no contesta (red, DNS, timeout): no hay nada que corregir, se reintenta.
pub const CLOUD_UNREACHABLE: &str = "cloud_unreachable";
/// El hub no está enrolado: sin credencial de máquina no puede administrar el acceso en el SaaS.
pub const NOT_ENROLLED: &str = "not_enrolled";

/// Mapea un [`MembersError`] a la respuesta HTTP del handler admin. El alta/baja **local** ya se
/// aplicó (idempotente); esto reporta que la parte SaaS falló, con un status honesto.
///
/// 🔴 hub#1214 — lo que sale por aquí es **código estable + frase redactada**, nunca el
/// `Display` del error: ese `Display` lleva dentro el **cuerpo crudo del SaaS**, y así es como
/// `el SaaS respondió 429: {"detail":"Request was throttled…"}` —inglés de DRF dentro de una
/// frase en español— acabó pintado en una pantalla en español (visto en prod, v1.1.9). Misma
/// política que el dispatcher desde hub#1074/#1186: la fontanería (aquí, la de OTRO sistema) va al
/// log del runtime; al navegador va un código que la pantalla traduce (ADR-0055).
///
/// El código viaja **dentro** de `error` (`{"ok":false,"error":{"code":…}}`), que es el envelope
/// del resto del runtime (`schemas/envelope.schema.json`): como hermano de `error`, una pantalla
/// que lee `error.code` no encontraba nada y caía a la prosa.
pub(crate) fn members_error_response(e: MembersError) -> Response {
    let (status, code) = match &e {
        // Bootstrap incompleto: el hub no está enrolado → no puede administrar el acceso en el SaaS.
        MembersError::NoMachineToken => (StatusCode::CONFLICT, NOT_ENROLLED),
        // 424, never a `5xx`: the hub is the ORIGIN, so an edge replaces the body of a `502`
        // with its own page and `cloud_unreachable` never reaches the staff tab (hub#1763).
        MembersError::Transport(_) => (cloud_proxy::CLOUD_FAILED, CLOUD_UNREACHABLE),
        // Un 429 NO es un rechazo de negocio: «espera y reintenta» y «arregla lo que has escrito»
        // son acciones opuestas para quien administra, así que llevan códigos distintos. Es el
        // mismo código que ya emite el proxy de entitlement (`entitlement::CLOUD_RATE_LIMITED`).
        MembersError::Cloud(429, _) => (
            StatusCode::TOO_MANY_REQUESTS,
            crate::entitlement::CLOUD_RATE_LIMITED,
        ),
        // Reenvía un 4xx del SaaS como 4xx (p. ej. email ya invitado); cualquier otro —incluido
        // un 5xx del SaaS, que relayado se lo comería el borde igual que uno acuñado aquí
        // (hub#1763)— se cuenta como «la dependencia falló».
        MembersError::Cloud(status, _) => (
            StatusCode::from_u16(*status)
                .ok()
                .filter(StatusCode::is_client_error)
                .unwrap_or(cloud_proxy::CLOUD_FAILED),
            CLOUD_REJECTED,
        ),
    };
    // El detalle —status y cuerpo del SaaS— SÍ se conserva, pero donde se puede leer sin
    // publicarlo: el log del runtime. Un fallo que no se ve no existe.
    tracing::warn!(code, error = %e, "no se pudo sincronizar el acceso con el SaaS");
    (
        status,
        Json(json!({ "ok": false, "error": { "code": code, "message": redacted_message(code) } })),
    )
        .into_response()
}

/// Frase de respaldo de cada código. Está en **inglés** y es fija a propósito (misma regla que
/// `error_payload`, hub#1074): la que ve el usuario la escribe la pantalla traduciendo el código
/// (ADR-0055), y esta solo sirve para un cliente antiguo y para el log.
fn redacted_message(code: &str) -> &'static str {
    match code {
        NOT_ENROLLED => "this hub is not enrolled: it cannot administer access in the Cloud",
        CLOUD_UNREACHABLE => "the Cloud did not answer while syncing access",
        crate::entitlement::CLOUD_RATE_LIMITED => {
            "the Cloud is rate-limiting this hub; access could not be synced"
        }
        _ => "the Cloud refused the access change",
    }
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
        // Mismo envelope y misma regla que el resto de la puerta (hub#1214): código estable dentro
        // de `error`, frase en inglés de respaldo. Antes salía una frase española suelta, fuera del
        // envelope, que ninguna pantalla podía traducir.
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": {
                "code": "invalid_payload",
                "message": "email and role are required",
            }})),
        )
            .into_response();
    }
    // Gate admin + alta local bajo el MISMO lock; se suelta ANTES de la I/O de red al SaaS.
    let user = {
        let rt = st.runtime.read().await;
        let actor = match auth::require_admin_session(&headers, &st.config, &rt).await {
            Ok(user) => user,
            Err(e) => return crate::unauthorized(e),
        };
        // Las mismas barandillas que Personal, antes de escribir nada (hub#1429, hub#1444). Esta
        // puerta escribe el rol sobre la fila que encuentra por email (`SET role = :role,
        // is_active = 1`), así que el equivalente exacto de lo que va a pasar es ese
        // `UpdateHubUser`: sin él, un alta con la dirección del dueño lo DEGRADA y el último
        // administrador puede degradarse a sí mismo dejando el hub sin nadie que lo administre.
        if let Some(response) = crate::hub_users::guard_members_door_by_email(
            &rt,
            &actor,
            &email,
            &erplora_runtime::hub_users::UpdateHubUser {
                role: Some(role.clone()),
                is_active: Some(true),
                ..Default::default()
            },
        )
        .await
        {
            return response;
        }
        // …y el plan tiene que tener plaza para una persona MÁS (hub#1685). Antes de escribir en
        // local y antes de llamar al SaaS: una invitación que el hub no puede sostener no sale.
        if let Some(response) = crate::hub_users::enforce_seat_for_email(&rt, &st, &email).await {
            return response;
        }
        let before = match crate::hub_users::census_row_by_access_email(&rt, &email).await {
            Ok(before) => before,
            Err(e) => return crate::err_response(e),
        };
        let user = match rt
            .create_login_user(&email, &role, crate::hub_users::plan_max_users(&st))
            .await
        {
            Ok(user) => user,
            Err(e) => return crate::err_response(e),
        };
        // hub#2571: rewriting the role of somebody already inside is a role change — their open
        // channels heard with the old one.
        if before.is_some_and(|u| u.is_active && u.role != role) {
            crate::hub_users::end_live_channels_of(&st, &user.id);
        }
        user
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
        let rt = st.runtime.read().await;
        let actor = match auth::require_admin_session(&headers, &st.config, &rt).await {
            Ok(user) => user,
            Err(e) => return crate::unauthorized(e),
        };
        // Y la baja tampoco: es la simetría de la misma puerta (hub#1429, hub#1444). Aquí lo que
        // se escribe es una desactivación, así que además de la fila del dueño decide
        // `self_deactivation` (nadie se da de baja a sí mismo) y `last_admin` (el hub no se queda
        // sin administrador activo).
        if let Some(response) = crate::hub_users::guard_members_door_by_email(
            &rt,
            &actor,
            &email,
            &erplora_runtime::hub_users::UpdateHubUser {
                is_active: Some(false),
                ..Default::default()
            },
        )
        .await
        {
            return response;
        }
        let before = match crate::hub_users::census_row_by_access_email(&rt, &email).await {
            Ok(before) => before,
            Err(e) => return crate::err_response(e),
        };
        let existed = match rt.deactivate_login_user(&email).await {
            Ok(existed) => existed,
            Err(e) => return crate::err_response(e),
        };
        // hub#2571: closed here, before erplora.com is told — the local door does not wait for it.
        if let Some(person) = before {
            crate::hub_users::end_live_channels_of(&st, &person.id);
        }
        existed
    };
    if let Err(e) = notify_member_removed(&st, &email).await {
        return members_error_response(e);
    }
    Json(json!({ "ok": true, "deactivated": existed })).into_response()
}

/// `GET /api/members` — lista los usuarios-login del hub para el panel admin. Gate **owner/admin**.
pub async fn list_members(State(st): State<AppState>, headers: axum::http::HeaderMap) -> Response {
    let rt = st.runtime.read().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return crate::unauthorized(e);
    }
    match rt.list_login_users().await {
        Ok(users) => Json(json!({ "ok": true, "members": users })).into_response(),
        Err(e) => crate::err_response(e),
    }
}
