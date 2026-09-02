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
    /// The session is perfectly valid — the ROLE is not enough (hub#660). It is a different answer
    /// from the two above: `401` invites the caller to authenticate, and re-authenticating as the
    /// same cashier will never help. Handlers that care about the distinction map this to `403`;
    /// every handler that predates it maps the whole enum to `401` and is unaffected.
    Forbidden(String),
}

impl AuthError {
    pub fn message(&self) -> String {
        match self {
            AuthError::MissingSession => "falta sesión (cabecera X-Hub-Session)".to_string(),
            AuthError::Invalid(e) => format!("no autenticado: {e}"),
            AuthError::Forbidden(e) => e.clone(),
        }
    }

    /// ¿Es un fallo de **rol** (sesión válida, permiso insuficiente) y no de autenticación?
    pub fn is_forbidden(&self) -> bool {
        matches!(self, AuthError::Forbidden(_))
    }
}

/// Token de sesión del hub (cabecera `X-Hub-Session`), si viene.
pub fn session_token(headers: &HeaderMap) -> Option<String> {
    header(headers, "x-hub-session")
}

/// Value of `name` in the request's `Cookie` header, if present.
///
/// The hub authenticates by header everywhere (ADR-0003), and this is not a second way in: the only
/// caller is the media READ door, because the only requests the app cannot put a header on are the
/// ones the browser issues by itself — `<img src>` and `background-image` (hub#791, ADR-0366). See
/// [`crate::media`] for why that door, and only that one, reads a cookie.
pub fn cookie(headers: &HeaderMap, name: &str) -> Option<String> {
    headers
        .get_all(axum::http::header::COOKIE)
        .iter()
        .filter_map(|v| v.to_str().ok())
        .flat_map(|line| line.split(';'))
        .filter_map(|pair| pair.split_once('='))
        .find(|(k, _)| k.trim() == name)
        .map(|(_, v)| v.trim().to_string())
        .filter(|v| !v.is_empty())
}

/// Step-up approval token of `X-Elevation-Token` (hub#361), if the caller presents one.
///
/// A **header**, not a payload field: the body of a command has to stay pure data, so that the
/// one thing a client contributes to an authorisation decision is a reference to a grant the
/// runtime already holds. It is not a credential the hub verifies here — an unknown, expired or
/// foreign token is simply not a grant, and the dispatcher answers exactly as if none had come.
pub fn elevation_token(headers: &HeaderMap) -> Option<String> {
    header(headers, "x-elevation-token").filter(|t| !t.is_empty())
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
    Ok(api_key_principal(headers, config, rt).await?.context)
}

/// Variante que conserva id y cuota; las superficies externas la usan para consumir el rate
/// limit durable antes de llegar al dispatcher.
pub async fn api_key_principal(
    headers: &HeaderMap,
    config: &HubConfig,
    rt: &Runtime,
) -> Result<erplora_runtime::api_keys::ApiKeyPrincipal, AuthError> {
    let token = api_key_token(headers).ok_or(AuthError::MissingSession)?;
    let _ = config; // hub_id lo aporta el runtime (despliegue); aquí solo documentamos el plano.
    rt.resolve_api_key(&token)
        .await
        .map_err(|e| AuthError::Invalid(e.to_string()))?
        .ok_or_else(|| AuthError::Invalid("API key inválida o revocada".into()))
}

/// Autentica una petición de la superficie **interna** y construye su `RequestContext` según el
/// modo configurado. Las API keys solo se aceptan en `/api/v1` y `/webhook`; rechazarlas aquí
/// evita saltarse el doble gate `expose_api` usando `/api/query` o `/api/command`.
/// - `Dev`: confía en cabeceras (`X-User-Id`/`X-Permissions`).
/// - `Session`: resuelve la sesión server-side → `hub_user` → permisos del rol (autoridad local).
pub async fn authenticate(
    headers: &HeaderMap,
    config: &HubConfig,
    rt: &Runtime,
) -> Result<RequestContext, AuthError> {
    if api_key_token(headers).is_some() {
        return Err(AuthError::Invalid(
            "la API key solo se admite en /api/v1 y /webhook".into(),
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
        // Authenticated, just not allowed → `Forbidden`, so a handler that tells the two apart can
        // answer `403`. Callers that map every `AuthError` to `401` keep behaving exactly as before.
        Err(AuthError::Forbidden(format!(
            "se requiere rol owner/admin para gestionar el Hub (rol actual: {})",
            user.role
        )))
    }
}

/// ¿El rol gestiona API keys? owner/admin (insensible a mayúsculas). Conjunto cerrado y conservador
/// (ADR-0057 §6: "gestionado por owner/admin"). Lo reusa `crate::hub_users` para no tener DOS
/// definiciones de "quién administra el hub" que puedan divergir.
///
/// La definición vive en el **runtime**, junto al catálogo de roles (`hub_users::BASE_ROLES`),
/// porque desde hub#347 también la necesita el suelo de rol del login cloud
/// (`identity::get_or_link_cloud_user`), que corre server-side pero dentro del runtime.
pub(crate) fn is_admin_role(role: &str) -> bool {
    erplora_runtime::hub_users::is_admin_role(role)
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
    machine_auth(st).or_else(|| {
        st.is_dev_hub()
            .then(|| user_auth(headers, &hub_id))
            .flatten()
    })
}

/// LOCAL role somebody is provisioned with the first time they come in from the Cloud.
///
/// The SaaS already sends the user's role in THIS hub, and it sends it twice for as long as the
/// transition lasts: the new key `hubs[].role` and the legacy `organizations[].role` mirror
/// (crossed with `hubs[].org`) — see `UserClaims::role_keys_for_hub`, hub#350. The Hub used to
/// ignore it and provision EVERYBODY with least privilege, so **an account admin walked into their
/// own hub as an `employee`**: unable to import a blueprint, manage users, or fix it from inside.
/// Only the email seeded at deploy time (`HUB_OWNER_EMAIL`) had privilege, so a second partner — or
/// the owner themselves signing in with another account — was locked out with no remedy.
///
/// Only the two roles the Hub itself recognises as administrative rise ([`is_admin_role`]), and
/// **always to `admin`, NEVER to `owner`**. Anything else — `manager`, `member`, `employee`, an
/// unknown one or none at all — falls back to the default role, which is still least privilege.
///
/// That the account owner comes in as `admin` and not as `owner` is deliberate: ADR-0157 fixed that
/// **hub ownership comes from the env seeded at deploy time (`HUB_OWNER_EMAIL`), not from a claim**,
/// and that invariant is kept whole. `admin` already solves the real problem — importing blueprints,
/// managing users, administering the hub — without hub ownership being derivable from a token.
///
/// It does not reopen the auto-admin ADR-0157 closed either: that promoted ANY SaaS user holding a
/// valid token; this requires being owner/admin **of this very hub**, signed by the SaaS.
///
/// It applies on EVERY login, not only on the first link: the account role is a **floor**
/// re-evaluated each time ([`role_floor_for_cloud_login`], hub#347). For a row that already exists
/// the floor only **rises**; it never lowers the local role and never grants `owner`.
///
/// `saas_roles` is **every** key the token carries for this hub
/// (`UserClaims::role_keys_for_hub`, hub#350): the contract travels in two shapes during the
/// transition and both are read. Empty = the token says nothing → default role.
pub fn local_role_for_cloud_login(saas_roles: &[String], default_role: &str) -> String {
    role_floor_for_cloud_login(saas_roles)
        .unwrap_or(default_role)
        .to_string()
}

/// **Floor** the ACCOUNT role imposes on the hub's local role, re-evaluated on **every** login
/// (plan step 2b rule C, hub#347). `None` = this account imposes no floor at all.
///
/// The local role used to be a snapshot of the moment the row was created: `get_or_link_cloud_user`
/// returned the existing row untouched, so promoting somebody in the SaaS never reached the hub.
/// Whoever logged in once before being promoted stayed an `employee` forever, unable to import a
/// blueprint or to fix it from inside.
///
/// The two planes remain **orthogonal** (ADR-0157 §6): the account role rules the ACCOUNT (buying,
/// paying, inviting) and the local role rules the BUSINESS (selling, discounting, closing the till).
/// The bridge between them is a floor, **not a synchronisation**: it raises to the agreed minimum
/// and leaves everything above it alone, so a login never overwrites the hub's own decisions.
///
/// Four invariants, all on the conservative side:
///
/// 1. **Only owner/admin rise** ([`is_admin_role`]) of the hub being entered (ADR-0201: membership
///    is per hub). `manager`, `member`, `employee`, an unknown one, an empty one or none → `None`:
///    belonging to the hub is not enough to administer it, which is the auto-admin ADR-0157 closed.
/// 2. **The floor is `admin`, NEVER `owner`.** Hub ownership comes from the env seeded at deploy
///    time (`HUB_OWNER_EMAIL`, ADR-0157) and cannot be derived from a token. `admin` already solves
///    the real problem — importing, managing users, administering the hub.
/// 3. **`HUB_DEFAULT_ROLE` is not a floor.** The default role is only used when provisioning a brand
///    new row ([`local_role_for_cloud_login`]); if it acted as a floor, setting it to `admin` would
///    re-promote on every login anybody the hub had deliberately demoted.
/// 4. **With both shapes of the contract in flight, ALL of them must grant** (hub#350). The token
///    carries the role under the new key (`hubs[].role`) and under the legacy mirror
///    (`organizations[].role`), and `UserClaims::role_keys_for_hub` reports both. The floor is
///    granted only if **every** key present is administrative: no shape may grant more than the
///    other allows. A token that administers through one and not the other is not a promotion — it
///    is a token the Hub cannot read as administration — so it administers nothing. `owner` vs
///    `admin` is **not** that case: both administer (the ACCOUNT plane keeps both, hub#349), so a
///    rename in flight that spells the same membership differently under each shape **still opens
///    the hub** — refusing would lock the owner out of their own business mid-rollout.
///
/// Empty list = the token says nothing about the role (older SaaS, or a hub with no role under
/// either shape) → no floor.
pub fn role_floor_for_cloud_login(saas_roles: &[String]) -> Option<&'static str> {
    let administers_everywhere =
        !saas_roles.is_empty() && saas_roles.iter().all(|r| is_admin_role(r));
    administers_everywhere.then_some(erplora_runtime::hub_users::CLOUD_ROLE_FLOOR)
}

#[cfg(test)]
mod local_role_tests {
    /// One role key, the shape every test below the transition cares about.
    fn role(saas_role: &str, default_role: &str) -> String {
        super::local_role_for_cloud_login(&[saas_role.to_string()], default_role)
    }

    #[test]
    fn the_owner_and_the_admin_of_the_account_come_in_as_admin() {
        // The case that was broken: account admin → `employee` inside their own hub.
        assert_eq!(role("admin", "employee"), "admin");
        // The account OWNER also comes in as `admin`, NOT as `owner`: hub ownership is fixed by the
        // env seeded at deploy time (ADR-0157) and cannot be derived from a token.
        assert_eq!(role("owner", "employee"), "admin");
    }

    #[test]
    fn the_cloud_role_is_accepted_in_any_capitalisation() {
        assert_eq!(role("Owner", "employee"), "admin");
        assert_eq!(role("ADMIN", "employee"), "admin");
    }

    #[test]
    fn every_other_role_stays_at_least_privilege() {
        // `manager` runs their day in the SaaS, but that is NOT administering the hub. `member` is
        // the key that replaces `manager`/`employee` on the account plane (saas#1158, hub#350) and
        // it is no more administrative than they were.
        for r in ["manager", "employee", "member", "whatever"] {
            assert_eq!(role(r, "employee"), "employee", "{r} must not rise");
        }
    }

    #[test]
    fn without_a_role_in_the_token_the_default_wins() {
        // Token from an older SaaS, or a hub whose `org` is not listed: nothing is granted.
        assert_eq!(
            super::local_role_for_cloud_login(&[], "employee"),
            "employee"
        );
        assert_eq!(
            super::local_role_for_cloud_login(&[], "cashier"),
            "cashier",
            "honours HUB_DEFAULT_ROLE"
        );
    }

    #[test]
    fn an_empty_role_does_not_rise() {
        assert_eq!(role("", "employee"), "employee");
    }
}

#[cfg(test)]
mod role_floor_tests {
    /// One role key — a token from before the rename, or from after the mirror is retired.
    fn floor(saas_role: &str) -> Option<&'static str> {
        super::role_floor_for_cloud_login(&[saas_role.to_string()])
    }

    /// Every role key a token carries for this hub (hub#350): the new `hubs[].role` and the legacy
    /// `organizations[].role` mirror, as `UserClaims::role_keys_for_hub` reports them.
    fn floor_of(keys: &[&str]) -> Option<&'static str> {
        let owned: Vec<String> = keys.iter().map(|k| (*k).to_string()).collect();
        super::role_floor_for_cloud_login(&owned)
    }

    #[test]
    fn owner_and_admin_of_the_hub_impose_an_admin_floor() {
        // Rule C (hub#347): owner/admin of the hub in the cloud means *at least* `admin` locally,
        // re-evaluated on every login — this is what makes a promotion reach the hub.
        assert_eq!(floor("admin"), Some("admin"));
        assert_eq!(floor("owner"), Some("admin"));
        assert_eq!(floor("Owner"), Some("admin"), "case-insensitive");
    }

    #[test]
    fn the_floor_is_never_owner() {
        // Even for an account owner. Hub ownership comes from `HUB_OWNER_EMAIL` (ADR-0157): a
        // token must never be able to write `owner` into `hub_user`.
        for r in ["owner", "OWNER", "admin"] {
            assert_ne!(floor(r), Some("owner"), "{r} must not grant ownership");
        }
    }

    #[test]
    fn no_administrative_role_imposes_no_floor_at_all() {
        // Belonging to the hub is not administering it — that is the auto-admin ADR-0157 closed.
        // `member` is the new key for the old `manager`/`employee` (hub#350); none grants a floor.
        for r in ["manager", "member", "employee", "cashier", "", "whatever"] {
            assert_eq!(floor(r), None, "{r} must not impose a floor");
        }
        // Token from an older SaaS, or a hub whose role is not in the token: nothing is granted.
        assert_eq!(floor_of(&[]), None);
    }

    #[test]
    fn the_default_role_is_not_a_floor() {
        // `HUB_DEFAULT_ROLE` only decides how a BRAND NEW row is provisioned. If it leaked into the
        // floor, setting it to `admin` would silently re-promote, on every login, anybody the hub
        // had deliberately demoted. The floor never reads it: the two are computed apart.
        assert_eq!(floor("employee"), None);
        assert_eq!(
            super::local_role_for_cloud_login(&["employee".to_string()], "admin"),
            "admin"
        );
    }

    // ── Two wire shapes at once (hub#350) ──────────────────────────────────────────────────────

    #[test]
    fn the_floor_needs_every_key_the_token_carries_to_be_administrative() {
        // The conservative rule. A token that administers under one key and does not under the
        // other cannot be read as a promotion: neither shape may grant more than the other allows,
        // so the answer is the least of the two, whichever key carries the higher role.
        assert_eq!(floor_of(&["member", "owner"]), None);
        assert_eq!(floor_of(&["owner", "member"]), None);
        assert_eq!(floor_of(&["admin", "employee"]), None);
        assert_eq!(
            floor_of(&["", "admin"]),
            None,
            "an empty key is not administrative"
        );
    }

    #[test]
    fn two_administrative_spellings_of_the_same_membership_still_impose_the_floor() {
        // The disagreement that is not an anomaly: the account plane keeps `owner` AND `admin` as
        // live keys that both administer, so a rename in flight spelling the same membership
        // differently under each shape must still open the hub. Refusing would lock the account
        // owner out of their own business mid-rollout.
        assert_eq!(floor_of(&["owner", "admin"]), Some("admin"));
        assert_eq!(floor_of(&["admin", "Owner"]), Some("admin"));
    }

    #[test]
    fn either_shape_alone_imposes_the_floor_it_always_did() {
        // The whole point of the deployment order: a token that carries the role under only ONE
        // shape — the legacy mirror today, the new key after saas#1177 — resolves identically.
        assert_eq!(floor_of(&["admin"]), Some("admin"));
        assert_eq!(floor_of(&["owner"]), Some("admin"));
        assert_eq!(floor_of(&["member"]), None);
    }
}
