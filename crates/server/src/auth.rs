//! Autenticación de la petición → `RequestContext` (ARQUITECTURA.md §2.3, §2.5, §2.9).
//!
//! Dos modos (`HubConfig::auth_mode`):
//!  - **Dev**: confía en `X-Hub-Id` + `X-User-Id` + `X-Permissions` que pone el frontend. Para
//!    desarrollo local sin Cloud.
//!  - **Session** (modelo real, §2.9): la **autoridad de identidad/permisos es LOCAL**. El login
//!    (PIN local o JWT de usuario cloud — ver handlers en `lib.rs`) abre una **sesión server-side**
//!    (`hub_session`) y devuelve un token opaco; cada petición lo manda en `X-Hub-Session` y aquí se
//!    resuelve a un `hub_user` y a los **permisos de su rol** (`role_permissions` de los módulos
//!    activos). El `hub_id` viene del **config de despliegue** (no del header, no spoofable).
//!
//! El JWT de usuario (RS256) es solo el **adaptador de login cloud** (`cloud_client::verify_user_jwt`
//! en el handler de login): prueba *quién* es el usuario cloud → se mapea a un `hub_user` local
//! (`get_or_link_cloud_user`) → se abre sesión. Nunca es la fuente de permisos.
use axum::http::HeaderMap;
use erplora_runtime::{RequestContext, Runtime};

use crate::state::{AppState, AuthMode, HubConfig};

const DEFAULT_HUB: &str = "local";
const DEFAULT_USER: &str = "local";

/// Error de autenticación. Se mapea a `401 Unauthorized` en los handlers.
#[derive(Debug)]
pub enum AuthError {
    MissingSession,
    Invalid(String),
}

impl AuthError {
    pub fn message(&self) -> String {
        match self {
            AuthError::MissingSession => "falta sesión (cabecera X-Hub-Session)".to_string(),
            AuthError::Invalid(e) => format!("no autenticado: {e}"),
        }
    }
}

/// Token de sesión del hub (cabecera `X-Hub-Session`), si viene.
pub fn session_token(headers: &HeaderMap) -> Option<String> {
    header(headers, "x-hub-session")
}

/// Bearer `erpl_live_<id>_<secret>` de una **API key** (`Authorization: Bearer …`), si viene y
/// tiene el prefijo de API key. Distinto del JWT de usuario (que también va en `Authorization:
/// Bearer` pero NO empieza por `erpl_live_`): así un endpoint sabe qué tipo de bearer le llega.
pub fn api_key_token(headers: &HeaderMap) -> Option<String> {
    bearer(headers).filter(|t| t.starts_with(erplora_runtime::api_keys::TOKEN_PREFIX))
}

/// **Tercer camino de auth** (ADR-0057, public-api.md §6): resuelve una **API key** a su
/// `RequestContext { hub_id, user_id="apikey:<id>", permissions }` — el MISMO contexto que ya
/// consume el dispatcher. Verifica el bearer `erpl_live_…` contra `hub_api_key` (secret argon2id +
/// status='active'), actualiza `last_used_at` y expande el scope a permisos contra el Registry.
/// El `hub_id` viene del despliegue (config, no spoofable), igual que en `Session`.
///
/// `Err(MissingSession)` si no hay un bearer de API key en la petición; `Err(Invalid)` si lo hay
/// pero no resuelve (token mal formado, key inexistente, revocada o secreto incorrecto) — el
/// handler lo mapea a 401. Es independiente del `auth_mode` (Dev/Session): la API pública se
/// autentica SIEMPRE por la key, no por cabeceras de dev ni por sesión local.
pub async fn api_key_context(
    headers: &HeaderMap,
    config: &HubConfig,
    rt: &Runtime,
) -> Result<RequestContext, AuthError> {
    let token = api_key_token(headers).ok_or(AuthError::MissingSession)?;
    let _ = config; // hub_id lo aporta el runtime (despliegue); aquí solo documentamos el plano.
    rt.resolve_api_key(&token)
        .await
        .map_err(|e| AuthError::Invalid(e.to_string()))?
        .ok_or_else(|| AuthError::Invalid("API key inválida o revocada".into()))
}

/// Autentica la petición y construye el `RequestContext` según el modo configurado.
/// - `Dev`: confía en cabeceras (`X-User-Id`/`X-Permissions`).
/// - `Session`: resuelve la sesión server-side → `hub_user` → permisos del rol (autoridad local).
pub async fn authenticate(
    headers: &HeaderMap,
    config: &HubConfig,
    rt: &Runtime,
) -> Result<RequestContext, AuthError> {
    // **Tercer camino** (ADR-0057): una petición con bearer de API key (`erpl_live_…`) se resuelve
    // SIEMPRE como API key, sea cual sea el `auth_mode`. Va primero porque su contexto (permisos =
    // scope expandido) es independiente de Dev/Session. Si el bearer no es de API key, sigue el
    // flujo normal de abajo (sesión / cabeceras dev).
    if api_key_token(headers).is_some() {
        return api_key_context(headers, config, rt).await;
    }
    match config.auth_mode {
        AuthMode::Dev => Ok(context_from_headers(headers)),
        AuthMode::Session => {
            let token = session_token(headers).ok_or(AuthError::MissingSession)?;
            let user = rt
                .resolve_session(&token)
                .await
                .map_err(|e| AuthError::Invalid(e.to_string()))?
                .ok_or_else(|| AuthError::Invalid("sesión inválida o caducada".into()))?;
            // hub_id del runtime (no del header, no spoofable). Durante el primer bootstrap puede
            // haber sido adoptado en caliente después de construir `HubConfig`.
            let perms = rt.session_permissions(&user.role);
            Ok(RequestContext::new(rt.hub_id().to_string(), user.id, perms))
        }
    }
}

/// Resuelve una **sesión de usuario válida** (interna), SIN exigir rol admin (ADR-0057 §4 refinado,
/// 2026-06-24): la usa el OpenAPI interno (`GET /api/v1/openapi.json`). Ver la doc del spec es
/// inofensivo (usarlo exige una API key con permiso, no la sesión); por eso cualquier usuario
/// logueado puede verlo, pero el anónimo no, y **el principal API-key tampoco** (un holder de key no
/// saca el spec interno completo por aquí — ese es el caso "integraciones" futuro, fuera de alcance).
///
/// - **API key** (`Authorization: Bearer erpl_live_…`): **rechaza** (`Err`). Aunque resolviese a un
///   contexto válido, esta puerta es para usuarios humanos logueados, no para el principal de máquina.
/// - **Dev**: concede (el modo dev ya confía en el frontend; sin sesión que resolver).
/// - **Session**: exige `X-Hub-Session` válido → `hub_user` (cualquier rol). Anónimo → `Err`.
pub async fn require_user_session(
    headers: &HeaderMap,
    config: &HubConfig,
    rt: &Runtime,
) -> Result<RequestContext, AuthError> {
    // Un bearer de API key NO da acceso al spec interno: se rechaza explícitamente.
    if api_key_token(headers).is_some() {
        return Err(AuthError::Invalid(
            "el spec interno requiere una sesión de usuario, no una API key".into(),
        ));
    }
    match config.auth_mode {
        AuthMode::Dev => Ok(context_from_headers(headers)),
        AuthMode::Session => {
            let token = session_token(headers).ok_or(AuthError::MissingSession)?;
            let user = rt
                .resolve_session(&token)
                .await
                .map_err(|e| AuthError::Invalid(e.to_string()))?
                .ok_or_else(|| AuthError::Invalid("sesión inválida o caducada".into()))?;
            let perms = rt.session_permissions(&user.role);
            Ok(RequestContext::new(rt.hub_id().to_string(), user.id, perms))
        }
    }
}

/// Resuelve una **sesión admin** (owner/admin) para operaciones de gestión del Hub: API keys,
/// settings, ficheros y ciclo de vida de módulos. Estas rutas NO se autentican con una API key ni
/// con el token de máquina, sino con la **sesión local** del humano (`X-Hub-Session`). Devuelve el
/// `HubUser` si la sesión es válida **y** su rol es owner/admin; si no, `Err`.
///
/// En `AuthMode::Dev` (sin Cloud, sin sesiones) se concede al usuario de dev: el modo dev ya
/// confía en el frontend (`X-Permissions=*` por defecto), así que no tiene sentido un gate de rol
/// más estricto que el resto de endpoints en ese modo.
pub async fn require_admin_session(
    headers: &HeaderMap,
    config: &HubConfig,
    rt: &Runtime,
) -> Result<erplora_runtime::identity::HubUser, AuthError> {
    if config.auth_mode == AuthMode::Dev {
        // Dev: identidad de cabecera, rol "admin" simbólico (no hay sesión server-side que resolver).
        let ctx = context_from_headers(headers);
        return Ok(erplora_runtime::identity::HubUser {
            id: ctx.user_id,
            name: "dev".into(),
            role: "admin".into(),
            cloud_user_id: None,
            is_active: true,
        });
    }
    let token = session_token(headers).ok_or(AuthError::MissingSession)?;
    let user = rt
        .resolve_session(&token)
        .await
        .map_err(|e| AuthError::Invalid(e.to_string()))?
        .ok_or_else(|| AuthError::Invalid("sesión inválida o caducada".into()))?;
    if is_admin_role(&user.role) {
        Ok(user)
    } else {
        Err(AuthError::Invalid(format!(
            "se requiere rol owner/admin para gestionar el Hub (rol actual: {})",
            user.role
        )))
    }
}

/// ¿El rol gestiona API keys? owner/admin (insensible a mayúsculas). Conjunto cerrado y conservador
/// (ADR-0057 §6: "gestionado por owner/admin"). Lo reusa `crate::hub_users` para no tener DOS
/// definiciones de "quién administra el hub" que puedan divergir.
pub(crate) fn is_admin_role(role: &str) -> bool {
    matches!(role.to_ascii_lowercase().as_str(), "owner" | "admin")
}

/// Modo Dev: confía en las cabeceras que pone el frontend (sin verificación). Solo desarrollo.
pub fn context_from_headers(headers: &HeaderMap) -> RequestContext {
    let hub = header(headers, "x-hub-id").unwrap_or_else(|| DEFAULT_HUB.to_string());
    let user = header(headers, "x-user-id").unwrap_or_else(|| DEFAULT_USER.to_string());
    let perms = header(headers, "x-permissions")
        .map(|s| {
            s.split(',')
                .map(|p| p.trim().to_string())
                .filter(|p| !p.is_empty())
                .collect::<Vec<_>>()
        })
        .unwrap_or_else(|| vec!["*".to_string()]); // dev: sin gateway, admin por defecto
    RequestContext::new(hub, user, perms)
}

fn header(headers: &HeaderMap, name: &str) -> Option<String> {
    headers
        .get(name)
        .and_then(|v| v.to_str().ok())
        .map(|s| s.to_string())
}

/// Extrae el token Bearer del header `Authorization`, si existe.
pub fn bearer(headers: &HeaderMap) -> Option<String> {
    header(headers, "authorization")
        .and_then(|h| h.strip_prefix("Bearer ").map(|t| t.trim().to_string()))
}

/// `X-Hub-Id` de la petición, con fallback al `hub_id` de despliegue (config).
pub fn hub_id(headers: &HeaderMap, fallback: &str) -> String {
    header(headers, "x-hub-id").unwrap_or_else(|| fallback.to_string())
}

/// Construye la credencial `Auth::UserJwt` (Bearer + `X-Hub-Id`) para hablar con el Cloud
/// en nombre del usuario activo (ARQUITECTURA.md §2.3). `None` si no hay JWT en la petición.
pub fn user_auth(headers: &HeaderMap, fallback_hub: &str) -> Option<cloud_client::Auth> {
    let access = bearer(headers)?;
    Some(cloud_client::Auth::UserJwt {
        hub_id: hub_id(headers, fallback_hub),
        access,
    })
}

/// Credencial de **máquina** del hub (`Auth::HubToken` = `X-Hub-Token` + `X-Hub-Id`), si el hub
/// está enrolado. Lee el token **vivo** del [`AppState`] (`machine_token`), no la config estática,
/// para que un enrol/rotación aplique sin reiniciar (§2.3, hot-reload). `None` si no hay token.
pub fn machine_auth(st: &AppState) -> Option<cloud_client::Auth> {
    st.machine_token()
        .map(|token| cloud_client::Auth::HubToken {
            hub_id: st.hub_id(),
            token,
        })
}

/// Credencial para llamadas **hub-scoped** al Cloud (marketplace, entitlement, install, asistente):
/// usa la identidad de máquina. El JWT del usuario solo es fallback en Demo/Dev; en cualquier
/// instalación real la ausencia de token significa que el bootstrap no terminó y se rechaza.
///
/// Desacopla "el hub puede llegar al Cloud" de "qué usuario está activo": un cajero solo-local
/// (sesión por PIN, sin JWT cloud) sigue pudiendo navegar el marketplace y refrescar el
/// entitlement porque el hub se autentica a sí mismo. El secreto de máquina NO viaja al navegador:
/// estas llamadas las hace el runtime (server-side).
pub fn hub_scoped_auth(headers: &HeaderMap, st: &AppState) -> Option<cloud_client::Auth> {
    let hub_id = st.hub_id();
    machine_auth(st).or_else(|| st.is_demo().then(|| user_auth(headers, &hub_id)).flatten())
}

/// Rol LOCAL con el que se provisiona a alguien que entra por primera vez desde el Cloud.
///
/// El SaaS ya manda el rol del usuario en la organización dueña del hub (claim `organizations`,
/// cruzado con `hubs[].org` — ver `UserClaims::role_for_hub`). Hasta ahora el Hub lo ignoraba y
/// provisionaba a TODO el mundo con el mínimo privilegio, así que **un admin de la organización
/// entraba en su propio hub como `employee`**: no podía importar un blueprint, ni gestionar
/// usuarios, ni arreglarlo desde dentro. Solo el email sembrado al desplegar (`HUB_OWNER_EMAIL`)
/// tenía privilegio, de modo que un segundo socio, o el mismo dueño entrando con otra cuenta,
/// quedaba fuera sin remedio.
///
/// Solo ascienden los dos roles que el propio Hub reconoce como administrativos
/// ([`is_admin_role`]), y **siempre a `admin`, NUNCA a `owner`**. Cualquier otro —`manager`,
/// `employee`, uno desconocido o ninguno— cae al rol por defecto, que sigue siendo el mínimo
/// privilegio.
///
/// Que el owner de la organización entre como `admin` y no como `owner` es deliberado: ADR-0157
/// fijó que **el owner del hub sale del env sembrado al desplegar (`HUB_OWNER_EMAIL`), no de un
/// claim**, y esa invariante se conserva entera. `admin` ya resuelve el problema real —importar
/// blueprints, gestionar usuarios, administrar el hub— sin que la propiedad del hub pueda
/// derivarse de un token.
///
/// Tampoco reabre el auto-admin que cerró ADR-0157: aquello ascendía a CUALQUIER usuario del SaaS
/// con un token válido; esto exige ser owner/admin **de la organización dueña de este hub**,
/// firmado por el SaaS.
///
/// Afecta únicamente al PRIMER enlace: `get_or_link_cloud_user` devuelve la fila existente sin
/// tocar su rol, así que una degradación hecha a mano en el hub sigue mandando.
pub fn local_role_for_cloud_login(saas_role: Option<&str>, default_role: &str) -> String {
    match saas_role {
        Some(r) if is_admin_role(r) => "admin".to_string(),
        _ => default_role.to_string(),
    }
}

#[cfg(test)]
mod rol_local_tests {
    use super::local_role_for_cloud_login as rol;

    #[test]
    fn el_owner_y_el_admin_de_la_organizacion_entran_como_admin() {
        // Es el caso que estaba roto: admin de la org → `employee` dentro del hub.
        assert_eq!(rol(Some("admin"), "employee"), "admin");
        // El OWNER de la org también entra como `admin`, NO como `owner`: la propiedad del hub la
        // fija el env sembrado al desplegar (ADR-0157) y no puede derivarse de un token.
        assert_eq!(rol(Some("owner"), "employee"), "admin");
    }

    #[test]
    fn el_rol_del_saas_llega_en_cualquier_capitalizacion() {
        assert_eq!(rol(Some("Owner"), "employee"), "admin");
        assert_eq!(rol(Some("ADMIN"), "employee"), "admin");
    }

    #[test]
    fn los_demas_roles_se_quedan_en_el_minimo_privilegio() {
        // `manager` gestiona su día a día en el SaaS, pero eso NO es administrar el hub.
        for r in ["manager", "employee", "member", "loquesea"] {
            assert_eq!(rol(Some(r), "employee"), "employee", "{r} no debe ascender");
        }
    }

    #[test]
    fn sin_rol_en_el_token_manda_el_por_defecto() {
        // Token de un SaaS anterior, o hub cuyo `org` no figura: no se concede nada.
        assert_eq!(rol(None, "employee"), "employee");
        assert_eq!(rol(None, "cajero"), "cajero", "respeta HUB_DEFAULT_ROLE");
    }

    #[test]
    fn un_rol_vacio_no_asciende() {
        assert_eq!(rol(Some(""), "employee"), "employee");
    }
}
