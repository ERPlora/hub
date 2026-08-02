//! **Personal (core)** — capa HTTP de `hub_user`: `/api/hub/users` + `/api/hub/roles`.
//!
//! La pantalla de Personal del Hub gestiona los usuarios REALES del hub, no los miembros del módulo
//! `staff` (módulo de negocio con su propia navegación: profesional reservable, comisiones,
//! horarios). Antes la pantalla llamaba a `staff.members.list`, así que en un hub sin ese módulo
//! salía «No se pudo cargar el personal» y el owner/administrador —que entra por Cloud y no tiene
//! PIN— no aparecía en ningún sitio.
//!
//! Auth (mismo criterio que el resto del Hub):
//!  - **Leer** (`GET`) = cualquier sesión de usuario: la pantalla está en la nav de todos y los
//!    nombres+roles ya son públicos en el grid de PIN del login.
//!  - **Escribir** (`POST`/`PUT`/`DELETE`) = sesión **owner/admin** (`require_admin_session`), igual
//!    que settings, ficheros, API keys y el ciclo de vida de módulos.
//!
//! Dos barandillas que el runtime no puede aplicar solo (necesitan saber *quién* pide): nadie se da
//! de baja a sí mismo, y el hub nunca se queda sin un owner/admin **activo** —ni por baja ni por
//! degradación de rol—. Viven en [`guard_decision`], una función **pura** sobre la lista ya leída.
//!
//! **El acceso lo administra el SaaS** (ADR-0157 §7): es la fuente de verdad de la identidad y de
//! la membresía `(usuario → org/hub)`. Por eso un usuario **con email** no se puede dar de alta ni
//! de baja solo en local — habría ficha sin invitación, y el invitado nunca podría entrar. Estos
//! handlers hacen lo MISMO que `/api/members`: escriben en local y **notifican** al SaaS con la
//! credencial de máquina. Orden local→SaaS: si el SaaS falla, lo local persiste (idempotente por
//! email) y se devuelve un status honesto para que el admin reintente, nunca un 200 silencioso.
//! Un usuario **solo-PIN** (personal de tienda, sin cuenta online) es identidad puramente local:
//! ahí el SaaS no pinta nada y no se le llama.
use axum::extract::{Path, State};
use axum::http::{HeaderMap, StatusCode};
use axum::response::{IntoResponse, Response};
use axum::Json;
use serde_json::json;

use erplora_runtime::hub_users::{HubUserRow, NewHubUser, UpdateHubUser};
use erplora_runtime::Runtime;

use crate::auth::{self, is_admin_role};
use crate::state::AppState;

fn unauthorized(e: auth::AuthError) -> Response {
    (
        StatusCode::UNAUTHORIZED,
        Json(json!({ "ok": false, "error": e.message() })),
    )
        .into_response()
}

/// `400` de una barandilla de gestión. No es un fallo de payload —el cuerpo es válido— sino un
/// estado que dejaría el hub inservible, así que no es un 422 del runtime.
fn rejected(message: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({ "ok": false, "error": { "code": "rejected", "message": message } })),
    )
        .into_response()
}

fn not_found() -> Response {
    (
        StatusCode::NOT_FOUND,
        Json(
            json!({ "ok": false, "error": { "code": "not_found", "message": "usuario no encontrado" } }),
        ),
    )
        .into_response()
}

fn ok(data: impl serde::Serialize) -> Response {
    Json(json!({ "ok": true, "data": data })).into_response()
}

/// Runtime de la organización dueña de este hub (ADR-0005: en el tier cloud compartido hay un pool
/// por org). Mismo criterio que `settings.rs`/`profile.rs`: la identidad es el `hub_id` del
/// **despliegue**, nunca una cabecera del cliente.
async fn runtime(st: &AppState) -> Result<std::sync::Arc<tokio::sync::Mutex<Runtime>>, Response> {
    st.runtime_for(&st.hub_id())
        .await
        .map_err(crate::tenant_rejected)
}

/// GET /api/hub/users — todos los usuarios del hub (activos e inactivos, con PIN y sin él).
pub async fn list_users(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.list_hub_users().await {
        Ok(users) => ok(users),
        Err(e) => crate::err_response(e),
    }
}

/// GET /api/hub/roles — roles del core (catálogo base ∪ módulos activos ∪ en uso).
pub async fn list_roles(State(st): State<AppState>, headers: HeaderMap) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.list_hub_roles().await {
        Ok(roles) => ok(roles),
        Err(e) => crate::err_response(e),
    }
}

/// POST /api/hub/users — alta `{name, email?, role, pin?}`. Auth = sesión admin.
pub async fn create_user(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(input): Json<NewHubUser>,
) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    if let Err(e) = auth::require_admin_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    let id = match rt.create_hub_user(&input).await {
        Ok(id) => id,
        Err(e) => return crate::err_response(e),
    };
    let created = match find(&rt, &id).await {
        Ok(Some(row)) => row,
        Ok(None) => return not_found(),
        Err(e) => return crate::err_response(e),
    };
    // Suelta el lock ANTES de la I/O de red al SaaS (mismo patrón que `members::add_member`).
    drop(rt);
    if !created.email.is_empty() {
        if let Err(e) = crate::members::notify_member_added(&st, &created.email, &created.role).await
        {
            return crate::members::members_error_response(e);
        }
    }
    ok(created)
}

/// PUT /api/hub/users/{id} — edición parcial `{name?, email?, role?, is_active?, pin?}`.
/// Auth = sesión admin. Aplica las barandillas antes de tocar nada.
pub async fn update_user(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
    Json(input): Json<UpdateHubUser>,
) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(user) => user,
        Err(e) => return unauthorized(e),
    };
    if let Some(response) = guard(&rt, &admin.id, &id, &input).await {
        return response;
    }
    let row = match rt.update_hub_user(&id, &input).await {
        Ok(row) => row,
        Err(e) => return crate::err_response(e),
    };
    drop(rt);
    // Un cambio de rol también viaja: el SaaS guarda el rol con la membresía (ADR-0157 §6).
    if let Some(failure) = sync_access(&st, &row, input.is_active == Some(false)).await {
        return failure;
    }
    ok(row)
}

/// DELETE /api/hub/users/{id} — **baja = desactivar**, nunca borrar: sesiones, auditoría
/// (`created_by`/`updated_by`) e historial de ventas apuntan a ese id. Auth = sesión admin.
pub async fn deactivate_user(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.lock().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(user) => user,
        Err(e) => return unauthorized(e),
    };
    let input = UpdateHubUser {
        is_active: Some(false),
        ..UpdateHubUser::default()
    };
    if let Some(response) = guard(&rt, &admin.id, &id, &input).await {
        return response;
    }
    let row = match rt.update_hub_user(&id, &input).await {
        Ok(row) => row,
        Err(e) => return crate::err_response(e),
    };
    drop(rt);
    if let Some(failure) = sync_access(&st, &row, true).await {
        return failure;
    }
    ok(row)
}

/// Refleja en el SaaS lo que acaba de cambiar en local para un usuario **con email** (ADR-0157 §7):
/// `revoked = true` revoca la membresía; si no, re-manda el alta —idempotente por email— para que
/// el rol de la membresía quede al día. `None` = nada que sincronizar o todo fue bien.
async fn sync_access(st: &AppState, row: &HubUserRow, revoked: bool) -> Option<Response> {
    if row.email.is_empty() {
        return None; // Identidad puramente local (personal de tienda con PIN).
    }
    let result = if revoked {
        crate::members::notify_member_removed(st, &row.email).await
    } else {
        crate::members::notify_member_added(st, &row.email, &row.role).await
    };
    result.err().map(crate::members::members_error_response)
}

async fn find(rt: &Runtime, id: &str) -> erplora_runtime::Result<Option<HubUserRow>> {
    Ok(rt.list_hub_users().await?.into_iter().find(|u| u.id == id))
}

/// Lee el estado actual y aplica [`guard_decision`]. `Some(response)` = rechazado.
async fn guard(
    rt: &Runtime,
    actor_id: &str,
    target_id: &str,
    input: &UpdateHubUser,
) -> Option<Response> {
    let users = match rt.list_hub_users().await {
        Ok(users) => users,
        Err(e) => return Some(crate::err_response(e)),
    };
    match guard_decision(&users, actor_id, target_id, input) {
        Some(Guard::NotFound) => Some(not_found()),
        Some(Guard::Rejected(message)) => Some(rejected(message)),
        None => None,
    }
}

/// Veredicto de las barandillas de gestión.
#[derive(Debug, PartialEq, Eq)]
enum Guard {
    NotFound,
    Rejected(&'static str),
}

/// Decide si un cambio sobre `target_id` es admisible, dado el censo actual y quién lo pide.
/// Pura a propósito: las reglas son la parte delicada y se testean sin BD ni HTTP.
fn guard_decision(
    users: &[HubUserRow],
    actor_id: &str,
    target_id: &str,
    input: &UpdateHubUser,
) -> Option<Guard> {
    let Some(target) = users.iter().find(|u| u.id == target_id) else {
        return Some(Guard::NotFound);
    };

    if input.is_active == Some(false) && target_id == actor_id {
        return Some(Guard::Rejected(
            "no puedes darte de baja a ti mismo; pídeselo a otro administrador",
        ));
    }

    // ¿El cambio le quita a este usuario la condición de administrador activo?
    let was_admin = target.is_active && is_admin_role(&target.role);
    let role_after = input.role.as_deref().unwrap_or(&target.role);
    let still_admin = input.is_active.unwrap_or(target.is_active) && is_admin_role(role_after);
    if was_admin && !still_admin {
        let other_admins = users
            .iter()
            .filter(|u| u.id != target_id && u.is_active && is_admin_role(&u.role))
            .count();
        if other_admins == 0 {
            return Some(Guard::Rejected(
                "el hub se quedaría sin ningún administrador activo: nombra antes a otro owner/admin",
            ));
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;

    fn user(id: &str, role: &str, is_active: bool) -> HubUserRow {
        HubUserRow {
            id: id.into(),
            name: id.into(),
            email: String::new(),
            role: role.into(),
            cloud_user_id: None,
            is_active,
            has_pin: false,
            created_at: "2026-08-02T10:00:00Z".into(),
        }
    }

    fn deactivate() -> UpdateHubUser {
        UpdateHubUser {
            is_active: Some(false),
            ..UpdateHubUser::default()
        }
    }

    fn set_role(role: &str) -> UpdateHubUser {
        UpdateHubUser {
            role: Some(role.into()),
            ..UpdateHubUser::default()
        }
    }

    #[test]
    fn unknown_target_is_not_found() {
        let census = [user("owner", "owner", true)];
        assert_eq!(
            guard_decision(&census, "owner", "fantasma", &deactivate()),
            Some(Guard::NotFound)
        );
    }

    #[test]
    fn nobody_deactivates_themselves() {
        let census = [user("owner", "owner", true), user("admin", "admin", true)];
        // Hay otro admin, así que lo único que lo bloquea es que sea uno mismo.
        assert!(matches!(
            guard_decision(&census, "owner", "owner", &deactivate()),
            Some(Guard::Rejected(msg)) if msg.contains("ti mismo")
        ));
        assert_eq!(
            guard_decision(&census, "owner", "admin", &deactivate()),
            None
        );
    }

    #[test]
    fn the_last_admin_can_be_neither_deactivated_nor_demoted() {
        let census = [user("owner", "owner", true), user("caja", "cashier", true)];
        assert!(matches!(
            guard_decision(&census, "caja", "owner", &deactivate()),
            Some(Guard::Rejected(msg)) if msg.contains("administrador")
        ));
        assert!(matches!(
            guard_decision(&census, "owner", "owner", &set_role("employee")),
            Some(Guard::Rejected(msg)) if msg.contains("administrador")
        ));
        // Un admin INACTIVO no cuenta como relevo.
        let census = [
            user("owner", "owner", true),
            user("ex", "admin", false),
            user("caja", "cashier", true),
        ];
        assert!(guard_decision(&census, "owner", "owner", &set_role("employee")).is_some());
    }

    #[test]
    fn with_a_second_admin_the_change_goes_through() {
        let census = [user("owner", "owner", true), user("ana", "admin", true)];
        assert_eq!(
            guard_decision(&census, "owner", "owner", &set_role("employee")),
            None
        );
        // Y tocar a alguien que nunca fue admin nunca dispara la barandilla.
        let census = [user("owner", "owner", true), user("caja", "cashier", true)];
        assert_eq!(
            guard_decision(&census, "owner", "caja", &set_role("employee")),
            None
        );
    }
}
