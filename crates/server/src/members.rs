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
//! NOTA(core — columna del humano): hoy el Hub **no** expone todavía un flujo de administración de
//! usuarios-login (dar de alta un `hub_user` por email + rol lo hace hoy, implícitamente, el gate de
//! `auth_cloud` al pasar la presencia). El **endpoint/handler admin** que INVOQUE estas funciones —
//! con su gate de permisos (owner/admin) y el alta/baja del `hub_user` local— toca el modelo de
//! permisos/comandos, que es columna del humano (ADR-0157: «la IA implementa alrededor»). Estas
//! funciones son la pieza «el runtime llama al SaaS» ya lista para engancharse cuando ese flujo
//! exista; ver el informe de la tarea para el estado abierto.

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
