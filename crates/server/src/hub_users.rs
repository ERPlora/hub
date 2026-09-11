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
//! Las barandillas que el runtime no puede aplicar solo (necesitan saber *quién* pide): nadie se da
//! de baja a sí mismo, nadie enrola su propia placa, el hub nunca se queda sin un owner/admin
//! **activo** —ni por baja ni por degradación de rol—, nadie reparte un rol por encima del suyo, y
//! **la fila del dueño de la cuenta solo la edita el dueño** (hub#1429). Viven en
//! [`guard_decision`], una función **pura** sobre la lista ya leída.
//!
//! **El acceso lo administra el SaaS** (ADR-0157 §7): es la fuente de verdad de la identidad y de
//! la membresía `(usuario → hub)`. Por eso un usuario **con email** no se puede dar de alta ni de
//! baja solo en local — habría ficha sin invitación, y el invitado nunca podría entrar. Estos
//! handlers hacen lo MISMO que `/api/members`: escriben en local y **notifican** al SaaS con la
//! credencial de máquina. El **orden** lo decide la dirección del cambio ([`apply_update`]):
//! conceder se le pregunta al SaaS ANTES de escribir en local (una negativa no puede dejar el
//! cambio aplicado y la pantalla diciendo que falló), revocar se aplica en local primero (cerrar una
//! puerta no depende de que el cloud esté en pie) y lo que el SaaS no sabe —PIN, placa, nombre— no
//! le pregunta nada. Un usuario **solo-PIN** (personal de tienda, sin cuenta online) es identidad
//! puramente local: ahí el SaaS no pinta nada y no se le llama.
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

/// Tope de usuarios del plan según el último entitlement verificado (hub#1685). `0` = ilimitado,
/// y también lo que sale con el candado envenenado o sin refresh previo: fail-open, como el resto
/// del gate — la autoridad del plan es el SaaS, no este proceso.
pub(crate) fn plan_max_users(st: &AppState) -> u32 {
    st.entitlement.read().map(|g| g.max_users()).unwrap_or(0)
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
    if let Some(Guard::Forbidden { code, message }) = grant_decision(&actor.role, &input.role) {
        return forbidden(code, message);
    }
    // …y el plan tiene que tener plaza (hub#1685). El tope lo trae el entitlement, que vive aquí y
    // no en el runtime; `0` (incluido «aún no hubo refresh exitoso») = sin tope.
    if let Err(e) = rt.enforce_user_limit(plan_max_users(&st)).await {
        return crate::err_response(e);
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
        if let Err(e) =
            crate::members::notify_member_added(&st, &created.email, &created.role).await
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
    apply_update(st, headers, &id, input).await
}

/// DELETE /api/hub/users/{id} — **baja = desactivar**, nunca borrar: sesiones, auditoría
/// (`created_by`/`updated_by`) e historial de ventas apuntan a ese id. Auth = sesión admin.
pub async fn deactivate_user(
    State(st): State<AppState>,
    headers: HeaderMap,
    Path(id): Path<String>,
) -> Response {
    apply_update(
        st,
        headers,
        &id,
        UpdateHubUser {
            is_active: Some(false),
            ..UpdateHubUser::default()
        },
    )
    .await
}

/// El cuerpo compartido de la edición y de la baja: barandillas → SaaS/local en el orden que le
/// toca a lo que se está cambiando → respuesta.
///
/// **El orden lo decide la DIRECCIÓN del cambio** (hub#1429), no una regla única:
///
///  - Lo que el SaaS administra (**conceder**: rol, email de la membresía, reactivación) se le
///    pregunta **ANTES** de escribir nada en local. Antes era al revés y una negativa volvía con el
///    cambio ya aplicado: la pantalla decía «no se pudo guardar» y el PIN sí había cambiado. Con el
///    403 que el SaaS devolvía a toda edición de la fila del owner (saas#1638) eso pasaba en cada
///    intento.
///  - **Revocar** (`is_active: false`) va al revés a propósito: cerrar una puerta no puede depender
///    de que el cloud esté en pie. La baja local se aplica primero y el `502` sigue contando que la
///    mitad de la membresía falló — que es justo lo que la pantalla ya traduce («el usuario queda
///    guardado aquí»).
///  - Y lo que el SaaS **no sabe** —PIN, placa, nombre— no se le pregunta siquiera: nada de eso
///    viaja en una membresía, y hacerlo depender de una llamada de red dejaba a un TPV sin poder
///    rotar un PIN con el cloud caído.
async fn apply_update(
    st: AppState,
    headers: HeaderMap,
    id: &str,
    input: UpdateHubUser,
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
    let target = match guard(&rt, &admin, id, &input).await {
        Ok(target) => target,
        Err(response) => return response,
    };
    // **Reactivar es dar de alta** (hub#1685): la baja liberó la plaza y puede haberla ocupado otro,
    // así que volver a entrar vuelve a pedirla. Editar a quien ya está dentro (rol, nombre, PIN) no
    // gasta ninguna: si el tope se mirase en toda escritura, un hub Gratis con sus tres usuarios no
    // podría volver a tocar a ninguno.
    if input.is_active == Some(true) && !target.is_active {
        if let Err(e) = rt.enforce_user_limit(plan_max_users(&st)).await {
            return crate::err_response(e);
        }
    }
    let plan = access_sync_plan(&target, &input);
    drop(rt); // Suelta el lock ANTES de la I/O de red (mismo patrón que `members::add_member`).

    if let AccessSync::Grant { email, role } = &plan {
        if let Err(e) = crate::members::notify_member_added(&st, email, role).await {
            return crate::members::members_error_response(e);
        }
    }

    let row = {
        let rt = arc.read().await;
        match rt.update_hub_user(id, &input).await {
            Ok(row) => row,
            Err(e) => return crate::err_response(e),
        }
    };

    if let AccessSync::Revoke { email } = &plan {
        if let Err(e) = crate::members::notify_member_removed(&st, email).await {
            return crate::members::members_error_response(e);
        }
    }
    ok(row)
}

async fn find(rt: &Runtime, id: &str) -> erplora_runtime::Result<Option<HubUserRow>> {
    Ok(rt.list_hub_users().await?.into_iter().find(|u| u.id == id))
}

/// **La MISMA decisión de Personal en la otra puerta del mismo cambio**: `/api/members`
/// (ADR-0157 §7), donde a la persona se la nombra por EMAIL y no por id.
///
/// Hace falta aquí, y entera, porque los dos handlers escriben directamente sobre la fila que
/// encuentran por email: `create_login_user` le pone el `role` (`SET role = :role, is_active = 1`)
/// y `deactivate_login_user` la desactiva. Sin esto quedaban abiertas las tres:
///
///  - la fila del **dueño** —un alta con su dirección y `role: employee` lo DEGRADA— (hub#1429);
///  - **`self_deactivation`** — un administrador se daba de baja a sí mismo (hub#1444);
///  - **`last_admin`** — y podía degradarse siendo el último, dejando el hub sin nadie que pudiera
///    instalar un módulo, tocar un ajuste ni reincorporar a nadie (hub#1444). `self_deactivation`
///    no lo cubre: una degradación no es una baja.
///
/// Cerrar una puerta y dejar la otra abierta no es media guarda: es ninguna — y por eso la decisión
/// es [`guard_decision`] literal, la misma función pura, y no una copia con sus propias reglas que
/// pueda derivar de la de Personal.
///
/// `input` es el `UpdateHubUser` **equivalente** a lo que el handler va a escribir. `Some(response)`
/// = rechazado, sin escribir nada.
pub(crate) async fn guard_members_door_by_email(
    rt: &Runtime,
    actor: &erplora_runtime::identity::HubUser,
    email: &str,
    input: &UpdateHubUser,
) -> Option<Response> {
    let users = match rt.list_hub_users().await {
        Ok(users) => users,
        Err(e) => return Some(crate::err_response(e)),
    };
    let Some(target_id) = census_id_by_access_email(&users, email) else {
        // Nadie en el censo lleva ese email: el alta va a CREAR la fila, así que no hay a quién
        // proteger — pero el rango sí se mira igual (hub#356: nadie reparte un rol por encima del
        // suyo), que es la única de las reglas que no habla de una fila existente.
        return match input.role.as_deref().and_then(|r| grant_decision(&actor.role, r)) {
            Some(Guard::Forbidden { code, message }) => Some(forbidden(code, message)),
            _ => None,
        };
    };
    match guard_decision(&users, &actor.id, &actor.role, &target_id, input) {
        Some(Guard::NotFound) => Some(not_found()),
        Some(Guard::Rejected { code, message }) => Some(rejected(code, message)),
        Some(Guard::Forbidden { code, message }) => Some(forbidden(code, message)),
        None => None,
    }
}

/// El tope del plan en la puerta de `/api/members` (hub#1685), que es **idempotente por email**:
/// `create_login_user` escribe sobre la fila que encuentra (`SET role = :role, is_active = 1`).
///
/// Por eso no vale mirar el tope siempre: reescribir el rol de quien YA está activo no suma a nadie
/// —y con el plan lleno es justo lo normal—, mientras que invitar a alguien nuevo o reincorporar a
/// quien estaba de baja sí. Gemelo de la decisión que toma [`apply_update`] con `is_active`.
pub(crate) async fn enforce_seat_for_email(
    rt: &Runtime,
    st: &AppState,
    email: &str,
) -> Option<Response> {
    let users = match rt.list_hub_users().await {
        Ok(users) => users,
        Err(e) => return Some(crate::err_response(e)),
    };
    let already_inside = census_id_by_access_email(&users, email)
        .and_then(|id| users.into_iter().find(|u| u.id == id))
        .is_some_and(|u| u.is_active);
    if already_inside {
        return None;
    }
    rt.enforce_user_limit(plan_max_users(st))
        .await
        .err()
        .map(crate::err_response)
}

/// El id de la fila del censo cuyo email de **ACCESO** es `email`.
///
/// Se compara contra `hub_user.email` a propósito y no contra el email que pinta Personal, que es un
/// `COALESCE` con el del perfil: el del perfil lo edita cada uno en «Mi perfil» y sin control de
/// unicidad, así que dejarlo decidir permitiría hacerse pasar por la fila de otro —la del dueño, la
/// del último administrador— con solo escribir su dirección. `hub_user.email` no: lo escriben el
/// aprovisionamiento, `/api/members` y el alta de Personal, y `ensure_email_is_free` impide que dos
/// filas del hub compartan uno. Es además el mismo email por el que estos handlers resuelven la
/// fila que van a escribir, así que la guarda y la escritura no pueden apuntar a filas distintas.
fn census_id_by_access_email(users: &[HubUserRow], email: &str) -> Option<String> {
    let email = email.trim();
    if email.is_empty() {
        return None;
    }
    users
        .iter()
        .find(|u| !u.email.is_empty() && u.email.eq_ignore_ascii_case(email))
        .map(|u| u.id.clone())
}

/// Qué hay que contarle al SaaS de esta edición (ADR-0157 §7). Pura: la decisión es la parte
/// delicada y se testea sin BD ni red.
#[derive(Debug, PartialEq, Eq)]
enum AccessSync {
    /// Nada que sincronizar: o la fila es identidad puramente local (personal de tienda con PIN, sin
    /// email), o lo que cambia —PIN, placa, nombre— no vive en ninguna membresía.
    Nothing,
    /// Alta/actualización de la membresía, **idempotente por email**: el SaaS guarda el rol junto a
    /// ella (ADR-0157 §6), así que un cambio de rol también viaja.
    Grant { email: String, role: String },
    /// Revocación de la membresía.
    Revoke { email: String },
}

fn access_sync_plan(target: &HubUserRow, input: &UpdateHubUser) -> AccessSync {
    let email = input
        .email
        .as_deref()
        .map(str::trim)
        .filter(|e| !e.is_empty())
        .unwrap_or(&target.email)
        .to_string();
    if email.is_empty() {
        return AccessSync::Nothing; // Identidad puramente local.
    }
    if input.is_active == Some(false) {
        return AccessSync::Revoke { email };
    }
    let role = input.role.as_deref().unwrap_or(&target.role);
    let changes_the_membership = role != target.role
        || !email.eq_ignore_ascii_case(&target.email)
        || (input.is_active == Some(true) && !target.is_active);
    if changes_the_membership {
        AccessSync::Grant {
            email,
            role: role.to_string(),
        }
    } else {
        AccessSync::Nothing
    }
}

/// Lee el estado actual y aplica [`guard_decision`]. `Err(response)` = rechazado; `Ok` devuelve la
/// fila tal y como está ANTES de la edición, que es contra lo que se decide qué sabe el SaaS.
async fn guard(
    rt: &Runtime,
    actor: &erplora_runtime::identity::HubUser,
    target_id: &str,
    input: &UpdateHubUser,
) -> Result<HubUserRow, Response> {
    let users = match rt.list_hub_users().await {
        Ok(users) => users,
        Err(e) => return Err(crate::err_response(e)),
    };
    match guard_decision(&users, &actor.id, &actor.role, target_id, input) {
        Some(Guard::NotFound) => Err(not_found()),
        Some(Guard::Rejected { code, message }) => Err(rejected(code, message)),
        Some(Guard::Forbidden { code, message }) => Err(forbidden(code, message)),
        // `guard_decision` ya ha probado que la fila existe: si no, habría devuelto `NotFound`.
        None => users
            .into_iter()
            .find(|u| u.id == target_id)
            .ok_or_else(not_found),
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
    ///
    /// Lleva su propio `code` desde hub#1429: son ya dos motivos distintos —el rango que reparte y
    /// la fila del dueño— y aplanarlos en uno le pediría a la pantalla que tradujese «no puedes» sin
    /// poder decir por qué, que es justo lo que `error.code` existe para evitar (hub#1070).
    Forbidden {
        code: &'static str,
        message: &'static str,
    },
}

/// Código estable del rechazo de [`grant_decision`] (namespace reservado del core, ADR-0192).
const ROLE_ABOVE_INVITER: &str = "hub.users.role_above_inviter";

/// Código estable de la barandilla de la fila del DUEÑO de la cuenta (hub#1429).
const OWNER_ROW_IS_THE_OWNERS: &str = "hub.users.owner_row";

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
        return Some(Guard::Forbidden {
            code: ROLE_ABOVE_INVITER,
            message: "only somebody who administers this hub can hand out administration",
        });
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

    // **La fila del DUEÑO de la cuenta solo la edita el dueño** (hub#1429). Va la PRIMERA porque es
    // la única regla sobre *a quién* se toca: las de abajo hablan de qué se cambia, y contestar
    // «dejarías el hub sin administrador» a quien intenta cambiarle el PIN al dueño describe el
    // problema equivocado.
    //
    // Es la mitad que el SaaS NO puede poner (el mismo argumento de `grant_decision`): el runtime
    // habla con él con la credencial de máquina, que `assert_can_manage_hub_member` trata con rango
    // de owner, así que allí un administrador y una cajera son la misma llamada. El 403 que el SaaS
    // devolvía a TODA edición de esta fila lo tapaba por accidente —y de paso impedía al dueño rotar
    // su propio PIN, pm#167—; al levantarlo (saas#1638/#1788) la puerta queda aquí o no queda.
    //
    // El mercado la pone igual: seis de ocho productos revisados —Shopify, Square, Toast,
    // Lightspeed, Vagaro y Business Central, los cuatro TPV entre ellos— dejan la ficha del dueño en
    // solo lectura para cualquier otro administrador y transfieren la propiedad por un flujo aparte
    // del plano de la cuenta. Los dos que no (Odoo, WordPress) lo documentan como riesgo, no como
    // diseño. Aquí la transferencia la hace el SaaS y llega por `HUB_OWNER_EMAIL`, que mueve la marca.
    if target.is_account_owner && target_id != actor_id {
        return Some(Guard::Forbidden {
            code: OWNER_ROW_IS_THE_OWNERS,
            message: "this is the account owner's record: only they can change it",
        });
    }

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
    //
    // ⚠️ Y no alcanza al DUEÑO de la cuenta (hub#1429). Desde que nadie más puede tocar su fila,
    // exigirle cuatro ojos para su propia placa significaría que el dueño **no puede tener placa
    // jamás** — la forma exacta de pm#167, donde un bloqueo indiscriminado dejó al dueño sin poder
    // rotar un PIN filtrado. Lo que la regla protege es la relación de auditoría entre un
    // administrador y el dueño del hub; por encima del dueño no hay nadie a quien proteger, y así lo
    // hace Square, donde el passcode del dueño se pone en su propia cuenta.
    if target_id == actor_id
        && !target.is_account_owner
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
            is_account_owner: false,
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
            Some(Guard::Rejected {
                code: "self_deactivation",
                ..
            })
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
            Some(Guard::Rejected {
                code: "self_badge_enrollment",
                ..
            })
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
            Some(Guard::Rejected {
                code: "last_admin",
                ..
            })
        ));
        assert!(matches!(
            guard_decision(&census, "owner", "admin", "owner", &set_role("employee")),
            Some(Guard::Rejected {
                code: "last_admin",
                ..
            })
        ));
        // Un admin INACTIVO no cuenta como relevo.
        let census = [
            user("owner", "owner", true),
            user("ex", "admin", false),
            user("caja", "cashier", true),
        ];
        assert!(
            guard_decision(&census, "owner", "admin", "owner", &set_role("employee")).is_some()
        );
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
                matches!(
                    grant_decision("manager", granted),
                    Some(Guard::Forbidden {
                        code: ROLE_ABOVE_INVITER,
                        ..
                    })
                ),
                "a manager cannot hand out `{granted}`"
            );
            assert!(matches!(
                grant_decision("employee", granted),
                Some(Guard::Forbidden {
                    code: ROLE_ABOVE_INVITER,
                    ..
                })
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
            Some(Guard::Forbidden {
                code: ROLE_ABOVE_INVITER,
                ..
            })
        ));
        // An administrator doing the same thing is the ordinary way to name a second one.
        assert_eq!(
            guard_decision(&census, "owner", "admin", "caja", &set_role("admin")),
            None
        );
        // An edit that does not touch the role never asks the question.
        assert_eq!(
            guard_decision(
                &census,
                "caja",
                "employee",
                "caja",
                &UpdateHubUser::default()
            ),
            None
        );
    }

    /// The row of the person who OWNS the account, as the deployment named them
    /// (`is_account_owner`, hub#1429).
    fn account_owner(id: &str) -> HubUserRow {
        HubUserRow {
            is_account_owner: true,
            ..user(id, "admin", true)
        }
    }

    fn set_pin(pin: &str) -> UpdateHubUser {
        UpdateHubUser {
            pin: Some(pin.into()),
            ..UpdateHubUser::default()
        }
    }

    /// hub#1429 — **the owner's row is edited by the owner and by nobody else.**
    ///
    /// Six of the eight products checked (Shopify, Square, Toast, Lightspeed, Vagaro, Business
    /// Central — every one of the four POS among them) make the account owner's record read-only
    /// for any other administrator: Lightspeed says it outright ("The Primary User account employee
    /// page cannot be edited by anyone other than the Primary User"), Square keeps the owner
    /// passcode in the owner's personal account instead of the Team screen, and Shopify refuses to
    /// remove the store owner at all. The two that allow it — Odoo and WordPress — document it as a
    /// hazard rather than a design.
    #[test]
    fn only_the_owner_edits_the_owners_row() {
        let census = [account_owner("ioan"), user("ana", "admin", true)];
        // Every field, one reason: another administrator is not the owner. The PIN is the one that
        // matters most — it is the credential that opens the till AS the owner.
        for change in [
            set_pin("4271"),
            set_role("employee"),
            deactivate(),
            set_badge("0009171456"),
            UpdateHubUser {
                name: Some("Otro".into()),
                ..UpdateHubUser::default()
            },
        ] {
            assert!(
                matches!(
                    guard_decision(&census, "ana", "admin", "ioan", &change),
                    Some(Guard::Forbidden {
                        code: OWNER_ROW_IS_THE_OWNERS,
                        ..
                    })
                ),
                "an administrator who is not the owner may not edit the owner's row: {change:?}"
            );
        }
        // …and the owner editing their own row is exactly what the screen is for.
        assert_eq!(
            guard_decision(&census, "ioan", "admin", "ioan", &set_pin("4271")),
            None
        );
        // The rule names ONE row: everybody else stays as manageable as before.
        assert_eq!(
            guard_decision(&census, "ioan", "admin", "ana", &set_pin("4271")),
            None
        );
    }

    /// The same rule from the other side: a **badge** on the owner's row would be a card that signs
    /// in AS the owner, which is the worst version of this escalation and not an exception to it.
    ///
    /// Which forces the other half: since nobody else may enrol it, four eyes on the owner's own
    /// badge (`self_badge_enrollment`, hub#658) would mean the owner can NEVER hold one — the very
    /// shape of pm#167, where a blanket block left the owner unable to rotate a leaked PIN. So the
    /// owner enrols their own, like Square, where the owner passcode is set in the owner's own
    /// account. The four-eyes rule protects the audit relationship between an administrator and the
    /// hub's owner; above the owner there is nobody for it to protect.
    #[test]
    fn the_owner_enrols_their_own_badge_and_nobody_enrols_it_for_them() {
        let census = [account_owner("ioan"), user("ana", "admin", true)];
        assert!(matches!(
            guard_decision(&census, "ana", "admin", "ioan", &set_badge("0009171456")),
            Some(Guard::Forbidden {
                code: OWNER_ROW_IS_THE_OWNERS,
                ..
            })
        ));
        assert_eq!(
            guard_decision(&census, "ioan", "admin", "ioan", &set_badge("0009171456")),
            None,
            "the owner is the only person who can give the owner a badge"
        );
        // Four eyes still bind everybody else, owner or not.
        assert!(matches!(
            guard_decision(&census, "ana", "admin", "ana", &set_badge("0009171456")),
            Some(Guard::Rejected {
                code: "self_badge_enrollment",
                ..
            })
        ));
    }

    /// How the `/api/members` door finds the row it is about to write (hub#1429, hub#1444): by the
    /// **access** email, case-insensitively and trimmed — the same lookup `create_login_user` and
    /// `deactivate_login_user` do, so the guard and the write can never land on different rows.
    #[test]
    fn the_census_row_is_found_by_its_access_email() {
        let census = [
            with_email(account_owner("ioan"), "Ioan@Example.com"),
            with_email(user("ana", "admin", true), "ana@example.com"),
            // Store staff: PIN only, no account. An empty address must match NOBODY, or every
            // lookup that came in blank would land on the first of them.
            user("luis", "employee", true),
        ];

        assert_eq!(
            census_id_by_access_email(&census, " ioan@example.com "),
            Some("ioan".to_string()),
        );
        assert_eq!(
            census_id_by_access_email(&census, "ana@example.com"),
            Some("ana".to_string())
        );
        assert_eq!(census_id_by_access_email(&census, "   "), None);
        assert_eq!(census_id_by_access_email(&census, "nadie@example.com"), None);
    }

    /// And from that row the decision is [`guard_decision`] itself — the SAME function Personal
    /// runs, not a copy that can drift from it. This is the shape of both defects: the owner's row
    /// reached by email (hub#1429), and the two handrails that were missing on this door (hub#1444).
    #[test]
    fn the_members_door_decides_with_the_very_rules_of_personal() {
        let census = [
            with_email(account_owner("ioan"), "ioan@example.com"),
            with_email(user("ana", "admin", true), "ana@example.com"),
            with_email(user("luis", "employee", true), "luis@example.com"),
        ];
        let demote = UpdateHubUser {
            role: Some("employee".into()),
            is_active: Some(true),
            ..UpdateHubUser::default()
        };

        // hub#1429 — the alta by email is how the owner got demoted.
        let ioan = census_id_by_access_email(&census, "ioan@example.com").unwrap();
        assert!(matches!(
            guard_decision(&census, "ana", "admin", &ioan, &demote),
            Some(Guard::Forbidden {
                code: OWNER_ROW_IS_THE_OWNERS,
                ..
            })
        ));

        // hub#1444 — nobody signs themselves out…
        let ana = census_id_by_access_email(&census, "ana@example.com").unwrap();
        assert!(matches!(
            guard_decision(&census, "ana", "admin", &ana, &deactivate()),
            Some(Guard::Rejected {
                code: "self_deactivation",
                ..
            })
        ));

        // …and the last administrator standing cannot demote themselves either. A demotion is not
        // a baja, so `self_deactivation` never sees it: `last_admin` is the one that has to.
        let alone = [
            with_email(user("ana", "admin", true), "ana@example.com"),
            with_email(user("luis", "employee", true), "luis@example.com"),
        ];
        assert!(matches!(
            guard_decision(&alone, "ana", "admin", "ana", &demote),
            Some(Guard::Rejected {
                code: "last_admin",
                ..
            })
        ));
        // With somebody else administering, the very same gesture is fine.
        assert_eq!(guard_decision(&census, "ana", "admin", &ana, &demote), None);
    }

    fn with_email(mut row: HubUserRow, email: &str) -> HubUserRow {
        row.email = email.into();
        row
    }

    /// hub#1429 — **what the SaaS is told, and therefore what has to be asked first.**
    ///
    /// The handler used to notify the SaaS on EVERY edit of a row with an email, after writing
    /// locally. That is how rotating a PIN — something no membership carries — ended up depending on
    /// a network call, and how a refusal came back with the change already applied.
    #[test]
    fn only_what_lives_in_a_membership_reaches_the_saas() {
        let ana = with_email(user("ana", "employee", true), "ana@example.com");

        // A PIN, a badge and a name are not part of a membership: nothing to sync.
        assert_eq!(
            access_sync_plan(&ana, &set_pin("4271")),
            AccessSync::Nothing
        );
        assert_eq!(
            access_sync_plan(&ana, &set_badge("0009171456")),
            AccessSync::Nothing
        );
        assert_eq!(
            access_sync_plan(
                &ana,
                &UpdateHubUser {
                    name: Some("Ana S.".into()),
                    ..UpdateHubUser::default()
                }
            ),
            AccessSync::Nothing
        );
        // Neither is a role that is not changing, nor an `is_active: true` on somebody active.
        assert_eq!(
            access_sync_plan(&ana, &set_role("employee")),
            AccessSync::Nothing
        );

        // The role travels with the membership (ADR-0157 §6), so a real change does.
        assert_eq!(
            access_sync_plan(&ana, &set_role("manager")),
            AccessSync::Grant {
                email: "ana@example.com".into(),
                role: "manager".into(),
            }
        );
        // A baja revokes it…
        assert_eq!(
            access_sync_plan(&ana, &deactivate()),
            AccessSync::Revoke {
                email: "ana@example.com".into()
            }
        );
        // …and reinstating somebody asks for the membership back.
        let inactive = with_email(user("ana", "employee", false), "ana@example.com");
        assert_eq!(
            access_sync_plan(
                &inactive,
                &UpdateHubUser {
                    is_active: Some(true),
                    ..UpdateHubUser::default()
                }
            ),
            AccessSync::Grant {
                email: "ana@example.com".into(),
                role: "employee".into(),
            }
        );
    }

    /// Store staff with a PIN and no account are purely local identity: the SaaS is never called for
    /// them, whatever changes — that half of ADR-0157 §7 does not move.
    #[test]
    fn a_pin_only_user_never_reaches_the_saas() {
        let marta = user("marta", "cashier", true); // no email at all
        for change in [set_pin("4271"), set_role("manager"), deactivate()] {
            assert_eq!(access_sync_plan(&marta, &change), AccessSync::Nothing);
        }
    }

    /// A hub that never booted with `HUB_OWNER_EMAIL` has no marked row (`is_account_owner` false
    /// everywhere). It keeps exactly today's rules instead of locking a row nobody can name.
    #[test]
    fn without_a_named_owner_nothing_new_is_refused() {
        let census = [user("ioan", "admin", true), user("ana", "admin", true)];
        assert_eq!(
            guard_decision(&census, "ana", "admin", "ioan", &set_pin("4271")),
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
