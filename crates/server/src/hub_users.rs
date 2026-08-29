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
fn rejected(code: &str, message: &str) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
    )
        .into_response()
}

/// `403` de una barandilla de **quién** puede hacer algo (hub#356). Lleva el **código estable** del
/// core, no el `rejected` genérico: la UI tiene que poder traducir el motivo, y «tú no puedes
/// conceder eso» no se arregla cambiando el formulario.
fn forbidden(code: &str, message: &str) -> Response {
    (
        StatusCode::FORBIDDEN,
        Json(json!({ "ok": false, "error": { "code": code, "message": message } })),
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
async fn runtime(st: &AppState) -> Result<crate::state::SharedRuntime, Response> {
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
    let rt = arc.read().await;
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
    let rt = arc.read().await;
    if let Err(e) = auth::require_user_session(&headers, &st.config, &rt).await {
        return unauthorized(e);
    }
    match rt.list_hub_roles().await {
        Ok(roles) => ok(roles),
        Err(e) => crate::err_response(e),
    }
}

/// Cuerpo de `PUT /api/hub/roles/{key}`: encender o apagar un rol del catálogo.
#[derive(serde::Deserialize)]
pub struct RoleActivation {
    pub active: bool,
}

/// PUT /api/hub/roles/{key} — activa o desactiva en ESTE hub un rol declarado por un módulo
/// (paso 2b, hub#352). Devuelve el catálogo ya actualizado.
///
/// Auth = sesión **admin**, igual que ajustes, ficheros, API keys y el ciclo de vida de módulos:
/// decidir qué roles existen en el negocio es administrarlo. Leerlo (`GET`) sigue siendo cualquier
/// sesión — los nombres de rol ya son públicos en el grid de PIN del login.
///
/// El runtime rechaza (422) tanto un rol **base** (siempre activo, no se apaga) como una clave que
/// **ningún módulo instalado declara**: esta puerta activa lo que hay en el catálogo, no inventa
/// roles nuevos.
pub async fn set_role_activation(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(key): Path<String>,
    Json(input): Json<RoleActivation>,
) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.read().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(user) => user,
        Err(e) => return unauthorized(e),
    };
    if let Err(e) = rt.set_role_active(&key, input.active, &admin.id).await {
        return crate::err_response(e);
    }
    match rt.list_hub_roles().await {
        Ok(roles) => ok(roles),
        Err(e) => crate::err_response(e),
    }
}

/// POST /api/hub/users — alta `{name, email?, role, pin?, local?}`. Auth = sesión admin.
///
/// Desde hub#356 el alta es **exhaustiva** (ver `hub_users::create` en el runtime): `local: true` es
/// el personal solo-PIN, y sin la casilla es un **usuario de cuenta** — email obligatorio, y esta
/// capa es la que dispara la **invitación** (`notify_member_added`, credencial de máquina). Quién
/// puede invitar sigue siendo `admin`; **con qué rol**, lo acota [`grant_decision`].
pub async fn create_user(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(input): Json<NewHubUser>,
) -> Response {
    let arc = match runtime(&st).await {
        Ok(arc) => arc,
        Err(response) => return response,
    };
    let rt = arc.read().await;
    let actor = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(user) => user,
        Err(e) => return unauthorized(e),
    };
    // Antes de escribir nada: nadie reparte un rol por encima del suyo (hub#356).
    if let Some(Guard::Forbidden(message)) = grant_decision(&actor.role, &input.role) {
        return forbidden(ROLE_ABOVE_INVITER, message);
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
    let rt = arc.read().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(user) => user,
        Err(e) => return unauthorized(e),
    };
    if let Some(response) = guard(&rt, &admin, &id, &input).await {
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
    let rt = arc.read().await;
    let admin = match auth::require_admin_session(&headers, &st.config, &rt).await {
        Ok(user) => user,
        Err(e) => return unauthorized(e),
    };
    let input = UpdateHubUser {
        is_active: Some(false),
        ..UpdateHubUser::default()
    };
    if let Some(response) = guard(&rt, &admin, &id, &input).await {
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
    actor: &erplora_runtime::identity::HubUser,
    target_id: &str,
    input: &UpdateHubUser,
) -> Option<Response> {
    let users = match rt.list_hub_users().await {
        Ok(users) => users,
        Err(e) => return Some(crate::err_response(e)),
    };
    match guard_decision(&users, &actor.id, &actor.role, target_id, input) {
        Some(Guard::NotFound) => Some(not_found()),
        Some(Guard::Rejected { code, message }) => Some(rejected(code, message)),
        Some(Guard::Forbidden(message)) => Some(forbidden(ROLE_ABOVE_INVITER, message)),
        None => None,
    }
}

/// Veredicto de las barandillas de gestión.
#[derive(Debug, PartialEq, Eq)]
enum Guard {
    NotFound,
    /// «Esto dejaría el hub inservible». `code` es estable (`self_deactivation`,
    /// `self_badge_enrollment`, `last_admin`) y es lo que viaja en `error.code` (hub#1070); el
    /// mensaje es el texto de respaldo.
    Rejected {
        code: &'static str,
        message: &'static str,
    },
    /// Lo que se pide es legítimo, pero **no para quien lo pide** (hub#356). Sale como `403` con el
    /// código estable del core para que la UI lo traduzca, no como el `400 rejected` de las otras
    /// dos barandillas: aquellas dicen «esto dejaría el hub inservible», esta dice «tú no».
    Forbidden(&'static str),
}

/// Código estable del rechazo de [`grant_decision`] (namespace reservado del core, ADR-0192).
const ROLE_ABOVE_INVITER: &str = "hub.users.role_above_inviter";

/// **Nadie concede un rol por encima del suyo** (hub#356). `None` = admisible.
///
/// Tiene que vivir **aquí**, y aquí es el único sitio donde puede: el runtime habla con el SaaS con
/// la **credencial de máquina**, a la que `assert_can_manage_hub_member` trata con rango de owner,
/// así que el SaaS no puede saber si quien pulsó fue el administrador o la cajera. O el hub vigila
/// qué puede repartir cada uno de los suyos, o no lo vigila nadie.
///
/// El rango es el único que el core posee de verdad: **administra el hub o no** ([`is_admin_role`]).
/// Un orden total sobre los roles que declaran los módulos no existe —`bartender` no está ni por
/// encima ni por debajo de `kitchen`— e inventarlo aquí sería una segunda respuesta, discrepante,
/// a lo que hub#351 ya resolvió. Así que la regla se lee: **administrar solo lo concede quien ya
/// administra**, que es la misma puerta que cerraron hub#347 (el suelo del login cloud) y hub#351
/// (un manifest nunca acuña administradores), vista desde la invitación.
///
/// Con el gate en `require_admin_session` el actor SIEMPRE administra, así que hoy no rechaza nada:
/// es la guarda que hace que ensanchar el gate al `manager` —lo que el modelo de roles del paso 2b
/// quiere— sea un cambio y no una catástrofe.
fn grant_decision(actor_role: &str, granted_role: &str) -> Option<Guard> {
    if is_admin_role(granted_role) && !is_admin_role(actor_role) {
        return Some(Guard::Forbidden(
            "only somebody who administers this hub can hand out administration",
        ));
    }
    None
}

/// Decide si un cambio sobre `target_id` es admisible, dado el censo actual y quién lo pide.
/// Pura a propósito: las reglas son la parte delicada y se testean sin BD ni HTTP.
fn guard_decision(
    users: &[HubUserRow],
    actor_id: &str,
    actor_role: &str,
    target_id: &str,
    input: &UpdateHubUser,
) -> Option<Guard> {
    let Some(target) = users.iter().find(|u| u.id == target_id) else {
        return Some(Guard::NotFound);
    };

    // La misma regla de rango que la invitación (hub#356), aquí porque sin esta mitad la otra es
    // teatro: se invita como `employee` y se asciende a `admin` un segundo después. El rol del
    // actor lo trae la SESIÓN, no el censo: quien pregunta es quien está autenticado, y buscarlo en
    // la lista daría «rol vacío» —y por tanto un 403— para una sesión que no tiene fila propia
    // (`AuthMode::Dev`, donde la identidad la aportan las cabeceras).
    if let Some(role) = input.role.as_deref() {
        if let Some(forbidden) = grant_decision(actor_role, role) {
            return Some(forbidden);
        }
    }

    if input.is_active == Some(false) && target_id == actor_id {
        return Some(Guard::Rejected {
            code: "self_deactivation",
            message: "no puedes darte de baja a ti mismo; pídeselo a otro administrador",
        });
    }

    // **Cuatro ojos para la placa** (hub#658, el extra de Toast en la decisión de mercado): nadie
    // se enrola su propia tarjeta. Es la única de las tres credenciales donde el alta y el uso son
    // el mismo gesto —pasarla— así que un administrador podría enrolar una segunda tarjeta a su
    // nombre, dejarla en un cajón y usarla después sin que la traza distinga quién la pasó. Con dos
    // personas en el alta, la tarjeta tiene siempre un emisor distinto de su portador.
    //
    // ⚠️ Solo el ALTA. **Revocar la propia placa se puede siempre** (`badge: Some("")`): quien
    // acaba de perder la tarjeta es la persona con más prisa por matarla, y hacerle buscar a otro
    // administrador convierte una pérdida en una ventana abierta. Es la misma asimetría que el
    // resto del subsistema — cerrar una puerta nunca necesita permiso, abrirla sí.
    if target_id == actor_id
        && input
            .badge
            .as_deref()
            .is_some_and(|badge| !badge.trim().is_empty())
    {
        return Some(Guard::Rejected {
            code: "self_badge_enrollment",
            message: "nadie da de alta su propia placa: pídeselo a otro administrador",
        });
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
            return Some(Guard::Rejected {
                code: "last_admin",
                message: "el hub se quedaría sin ningún administrador activo: nombra antes a otro owner/admin",
            });
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
            has_badge: false,
            created_at: "2026-08-02T10:00:00Z".into(),
            // Estas pruebas son del guardarraíl «no te quedes sin administrador»: el conflicto de
            // email de acceso (hub#463) no entra en esa decisión.
            access_email_conflict: None,
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
            guard_decision(&census, "owner", "admin", "fantasma", &deactivate()),
            Some(Guard::NotFound)
        );
    }

    #[test]
    fn nobody_deactivates_themselves() {
        let census = [user("owner", "owner", true), user("admin", "admin", true)];
        // Hay otro admin, así que lo único que lo bloquea es que sea uno mismo.
        assert!(matches!(
            guard_decision(&census, "owner", "admin", "owner", &deactivate()),
            Some(Guard::Rejected { code: "self_deactivation", .. })
        ));
        assert_eq!(
            guard_decision(&census, "owner", "admin", "admin", &deactivate()),
            None
        );
    }

    fn set_badge(badge: &str) -> UpdateHubUser {
        UpdateHubUser {
            badge: Some(badge.into()),
            ..UpdateHubUser::default()
        }
    }

    /// hub#658 — **four eyes on a badge**, the extra Toast adds to the market decision.
    ///
    /// A badge is the only credential whose enrolment and whose use are the same gesture: swiping
    /// it. An administrator could therefore enrol a second card in their own name, leave it in a
    /// drawer and use it later — and the trace, which is the whole point of this credential, would
    /// name them either way with nothing to distinguish who held the card.
    #[test]
    fn nobody_enrols_their_own_badge() {
        let census = [user("owner", "owner", true), user("sofia", "manager", true)];
        assert!(matches!(
            guard_decision(&census, "owner", "admin", "owner", &set_badge("0009171456")),
            Some(Guard::Rejected { code: "self_badge_enrollment", .. })
        ));
        // …but enrolling somebody else's is exactly what an administrator is for.
        assert_eq!(
            guard_decision(&census, "owner", "admin", "sofia", &set_badge("0009171456")),
            None
        );
    }

    /// And the other half of the same rule: **revoking your own badge is always allowed.**
    /// Whoever just lost the card is the person in the biggest hurry to kill it; sending them to
    /// find a second administrator turns a loss into an open window.
    #[test]
    fn anybody_may_revoke_their_own_badge() {
        let census = [user("owner", "owner", true), user("sofia", "manager", true)];
        assert_eq!(
            guard_decision(&census, "owner", "admin", "owner", &set_badge("")),
            None
        );
        assert_eq!(
            guard_decision(&census, "owner", "admin", "owner", &set_badge("   ")),
            None,
            "a field of spaces is a revocation, not an enrolment"
        );
    }

    #[test]
    fn the_last_admin_can_be_neither_deactivated_nor_demoted() {
        let census = [user("owner", "owner", true), user("caja", "cashier", true)];
        assert!(matches!(
            guard_decision(&census, "caja", "cashier", "owner", &deactivate()),
            Some(Guard::Rejected { code: "last_admin", .. })
        ));
        assert!(matches!(
            guard_decision(&census, "owner", "admin", "owner", &set_role("employee")),
            Some(Guard::Rejected { code: "last_admin", .. })
        ));
        // Un admin INACTIVO no cuenta como relevo.
        let census = [
            user("owner", "owner", true),
            user("ex", "admin", false),
            user("caja", "cashier", true),
        ];
        assert!(guard_decision(&census, "owner", "admin", "owner", &set_role("employee")).is_some());
    }

    /// hub#356 — **nobody hands out a role above their own.**
    ///
    /// This has to live in the hub, and it is the only place it can: the runtime talks to the SaaS
    /// with the **machine credential**, which `assert_can_manage_hub_member` treats as owner rank,
    /// so the SaaS cannot tell whether the person who clicked was the administrator or the cashier.
    /// Either the hub polices which of its own people may grant what, or nobody does.
    ///
    /// The rank is the only one the core actually owns: *administers the hub* or not
    /// (`is_admin_role`). A total order over module-declared roles does not exist — `bartender` is
    /// neither above nor below `kitchen` — and inventing one here would be a second, disagreeing
    /// answer to a question hub#351 already settled.
    #[test]
    fn nobody_grants_a_role_above_their_own() {
        // Administration is granted only by somebody who already administers. This is the same
        // door hub#347 (the cloud role floor) and hub#351 (a manifest never mints administrators)
        // closed, seen from the invitation.
        for granted in ["admin", "owner", "ADMIN"] {
            assert!(
                matches!(grant_decision("manager", granted), Some(Guard::Forbidden(_))),
                "a manager cannot hand out `{granted}`"
            );
            assert!(matches!(
                grant_decision("employee", granted),
                Some(Guard::Forbidden(_))
            ));
            // …and an administrator can: inviting another administrator is the legitimate door of
            // ADR-0157 §7, and refusing it would leave a hub unable to name a second owner.
            assert_eq!(grant_decision("admin", granted), None);
            assert_eq!(grant_decision("owner", granted), None);
        }
        // Anything that does not administer is grantable by anyone who got through the gate: this
        // guard is about the administrative step, not about ranking the shop floor.
        for granted in ["manager", "employee", "bartender", "kitchen", ""] {
            assert_eq!(grant_decision("employee", granted), None, "{granted}");
            assert_eq!(grant_decision("admin", granted), None, "{granted}");
        }
    }

    /// The same rule on the **edit**, or the first half is theatre: invite as `employee`, promote
    /// to `admin` one second later. It is the argument that made hub#355 check the PIN on change
    /// as well as on create.
    #[test]
    fn the_same_rank_rule_applies_when_a_role_is_changed() {
        let census = [user("owner", "admin", true), user("caja", "employee", true)];
        // A non-administrator promoting somebody to administrator, through the edit door.
        assert!(matches!(
            guard_decision(&census, "caja", "employee", "caja", &set_role("admin")),
            Some(Guard::Forbidden(_))
        ));
        // An administrator doing the same thing is the ordinary way to name a second one.
        assert_eq!(
            guard_decision(&census, "owner", "admin", "caja", &set_role("admin")),
            None
        );
        // An edit that does not touch the role never asks the question.
        assert_eq!(
            guard_decision(&census, "caja", "employee", "caja", &UpdateHubUser::default()),
            None
        );
    }

    #[test]
    fn with_a_second_admin_the_change_goes_through() {
        let census = [user("owner", "owner", true), user("ana", "admin", true)];
        assert_eq!(
            guard_decision(&census, "owner", "admin", "owner", &set_role("employee")),
            None
        );
        // Y tocar a alguien que nunca fue admin nunca dispara la barandilla.
        let census = [user("owner", "owner", true), user("caja", "cashier", true)];
        assert_eq!(
            guard_decision(&census, "owner", "admin", "caja", &set_role("employee")),
            None
        );
    }
}
