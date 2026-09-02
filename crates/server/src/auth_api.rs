//! Auth endpoints: PIN, badge, cloud session, courier and logout — split out of `lib.rs` verbatim (hub#1404).

use crate::*;

#[derive(serde::Deserialize)]
pub(crate) struct PinReq {
    name: String,
    pin: String,
    /// Id estable del dispositivo (lo aporta el host: Tauri = id de máquina; web-PWA = id
    /// persistido). Opcional: solo lo usa el gate de device-trust si está activo (hub#15, §2.9).
    #[serde(default)]
    device_id: Option<String>,
}

#[derive(serde::Deserialize)]
pub(crate) struct CloudLoginReq {
    #[serde(default)]
    name: Option<String>,
    /// Email inicial de la identidad Cloud. Solo si el perfil local aún no tiene uno: después el
    /// usuario es dueño de sus datos y un login no pisa una edición hecha en Perfil.
    #[serde(default)]
    email: Option<String>,
    /// Id del dispositivo a marcar de confianza tras este login online (§2.9). Opcional.
    #[serde(default)]
    device_id: Option<String>,
}

/// Login local por **PIN** → abre sesión. Body `{name, pin, device_id?}` → `{ok, token, user}`
/// (401 si falla). Con **device-trust armado** (por defecto; `HUB_DEVICE_TRUST=off` lo desarma) el
/// PIN se rechaza si el cliente no identifica el dispositivo o si ese dispositivo no es de
/// confianza — no hubo login online previo en él (§2.9, hub#330).
///
/// **Los dos rechazos son distintos a propósito**, y no es un oráculo: el que llama ya sabe si mandó
/// un id o no, así que separarlos no le dice nada que no supiera, y sí le dice a la pantalla cuál de
/// las **dos** frases enseñar («este navegador no puede identificarse» ≠ «entra una vez con tu
/// cuenta aquí»). Lo que sí se mantiene indistinguible es *desconocido* de *revocado*: los dos son
/// `device_untrusted`, con el mismo texto, para que la puerta no confirme si alguien cortó un
/// dispositivo perdido (ADR-0258).
pub(crate) async fn auth_pin(State(st): State<AppState>, Json(req): Json<PinReq>) -> Response {
    let rt = st.runtime.read().await;
    // Qué dispositivo dice ser este cliente. **Se normaliza una sola vez** y de aquí sale todo lo
    // demás: una cabecera de espacios es un cliente que no se identificó, y tiene que caer en la
    // misma rama que no mandar nada — nunca en una búsqueda de `"  "` ni, con la puerta desarmada,
    // en una sesión cuyo dispositivo es la cadena vacía. Espejo de `device_mode::device_id_of`.
    let device_id = req
        .device_id
        .as_deref()
        .map(str::trim)
        .filter(|id| !id.is_empty());
    if let Some(refusal) = device_trust_gate(&st, &rt, device_id).await {
        return refusal;
    }
    // Brute-force guard (hub#329): checked BEFORE verifying, so a locked identity stops leaking
    // the right/wrong signal an attacker is fishing for.
    if let Some(retry_after_secs) = st.login_throttle.locked_for(&req.name) {
        return too_many_attempts(retry_after_secs);
    }
    match rt.verify_pin(&req.name, &req.pin).await {
        Ok(Some(user)) => {
            st.login_throttle.record_success(&req.name);
            // Límite de dispositivos del plan (ADR-0154): lo aporta el estado de entitlement del
            // server (fail-open a 0 = ilimitado si el lock está envenenado o aún no hubo refresh).
            let max_devices = st.entitlement.read().map(|g| g.max_devices()).unwrap_or(0);
            mint_session(
                &rt,
                user,
                device_id,
                max_devices,
                &erplora_runtime::identity::Credential::pin(),
            )
            .await
        }
        Ok(None) => {
            st.login_throttle.record_failure(&req.name);
            (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": "usuario o PIN incorrecto" })),
            )
                .into_response()
        }
        Err(e) => err_response(e),
    }
}

/// `429` de la guarda de fuerza bruta, idéntico en las dos puertas de login local.
pub(crate) fn too_many_attempts(retry_after_secs: u64) -> Response {
    (
        StatusCode::TOO_MANY_REQUESTS,
        Json(json!({
            "ok": false,
            "error": "demasiados intentos fallidos: espera unos minutos",
            "code": "too_many_attempts",
            "retry_after_secs": retry_after_secs
        })),
    )
        .into_response()
}

/// El gate de **device-trust** (§2.9, hub#330), compartido por las dos credenciales locales.
///
/// Vive en una función y no duplicado en cada puerta porque una placa que se saltase este gate
/// sería, literalmente, la vuelta atrás de hub#330: el hub responde en la internet pública y una
/// tarjeta se clona con un Flipper Zero. `None` = puede pasar.
pub(crate) async fn device_trust_gate(
    st: &AppState,
    rt: &erplora_runtime::Runtime,
    device_id: Option<&str>,
) -> Option<Response> {
    if st.config.device_trust_enforce {
        // No `device_id`, no bypass (hub#330): the check used to sit in an `if let Some(..)` with
        // no `else`, so leaving the field out walked past the gate entirely. The hub lives on the
        // public internet, so an unidentified device is the shape of the attack, not an oversight.
        let Some(device_id) = device_id else {
            return Some(
                (
                    StatusCode::FORBIDDEN,
                    Json(json!({
                        "ok": false,
                        "error": "this client did not identify its device",
                        "code": "device_unidentified"
                    })),
                )
                    .into_response(),
            );
        };
        match rt.is_device_trusted(device_id).await {
            Ok(true) => {}
            Ok(false) => {
                // Demo hubs adopt the FIRST device that shows up (hub#630). A demo visitor has no
                // account, and an online cloud login is the only thing that otherwise earns a
                // device its trust — so without this the PIN door on a demo could never be opened
                // by anybody: the hub came up, the seeded `Demo` user was there, and every login
                // answered `device_untrusted` until the reaper destroyed it.
                //
                // First use, not "off". The gate stays enforced and only the empty case is
                // special: once a device is adopted, the next one is refused exactly as always, so
                // whoever opened the demo keeps it and somebody who later guesses the URL does not
                // walk into their session. `Registry::demo_hub` is sealed at boot from `HUB_DEMO`
                // and has no writer (ADR-0197 §4), so this cannot be turned on from outside.
                //
                // The rule itself lives in `device_mode::demo_would_adopt`, SHARED with the read
                // door that decides whether the pinpad is painted (hub#514): when the two drifted,
                // this branch became unreachable — no pinpad, no PIN submit, no adoption.
                let adopt = match device_mode::demo_would_adopt(st.config.demo, rt, device_id).await
                {
                    Ok(adopt) => adopt,
                    Err(e) => return Some(err_response(e)),
                };
                if !adopt {
                    return Some(
                        (
                            StatusCode::FORBIDDEN,
                            Json(json!({
                                "ok": false,
                                "error": "this device has not signed in with an account yet",
                                "code": "device_untrusted"
                            })),
                        )
                            .into_response(),
                    );
                }
                if let Err(e) = rt.trust_device(device_id, "Demo (first device)").await {
                    return Some(err_response(e));
                }
            }
            Err(e) => return Some(err_response(e)),
        }
    }
    None
}

#[derive(serde::Deserialize)]
pub(crate) struct BadgeReq {
    /// Lo que el lector escribió como ráfaga de teclado (o lo que se tecleó, para un iButton).
    badge: String,
    #[serde(default)]
    device_id: Option<String>,
}

/// Login local por **PLACA** → abre sesión. Body `{badge, device_id?}` → `{ok, token, user}`
/// (401 si falla). hub#658.
///
/// La placa resuelve la identidad ENTERA: sustituye al par (nombre, PIN) del pinpad, nunca al PIN
/// solo. Por eso este cuerpo no lleva nombre — y por eso la respuesta no dice nunca si la tarjeta
/// existe: un 401 igual para «esa placa no es de nadie» y «esa placa es de alguien dado de baja».
///
/// **Las tres barandillas del PIN se mantienen enteras**: el mismo gate de device-trust
/// ([`device_trust_gate`]), la misma guarda de fuerza bruta y el mismo límite de dispositivos del
/// plan. La guarda se cuenta contra el **índice** de la tarjeta y no contra un nombre —aquí no hay
/// nombre que teclear— y eso además la hace más precisa: bloquea la tarjeta que se está probando,
/// sin que nadie pueda dejar fuera a un compañero pasando cinco veces una tarjeta rota a su nombre.
pub(crate) async fn auth_badge(State(st): State<AppState>, Json(req): Json<BadgeReq>) -> Response {
    let rt = st.runtime.read().await;
    let device_id = req
        .device_id
        .as_deref()
        .map(str::trim)
        .filter(|id| !id.is_empty());
    if let Some(refusal) = device_trust_gate(&st, &rt, device_id).await {
        return refusal;
    }
    // La clave del índice para poder acotar los intentos SIN guardar el número de la tarjeta en
    // ninguna estructura del servidor: lo que entra en el contador es el índice, que ya es lo que
    // la traza guarda.
    let throttle_key = match rt.badge_index_key().await {
        Ok(key) => format!(
            "badge:{}",
            erplora_runtime::identity::badge_index(&key, &req.badge)
        ),
        Err(e) => return err_response(e),
    };
    if let Some(retry_after_secs) = st.login_throttle.locked_for(&throttle_key) {
        return too_many_attempts(retry_after_secs);
    }
    match rt.verify_badge(&req.badge).await {
        Ok(Some(matched)) => {
            st.login_throttle.record_success(&throttle_key);
            let max_devices = st.entitlement.read().map(|g| g.max_devices()).unwrap_or(0);
            mint_session(
                &rt,
                matched.user,
                device_id,
                max_devices,
                &erplora_runtime::identity::Credential::badge(&matched.badge_index),
            )
            .await
        }
        Ok(None) => {
            st.login_throttle.record_failure(&throttle_key);
            (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": "placa no reconocida", "code": "badge_rejected" })),
            )
                .into_response()
        }
        Err(e) => err_response(e),
    }
}

/// Login de **usuario cloud**: verifica el JWT (RS256) y lo mapea a un `hub_user` local (lo
/// provisiona si es la primera vez), abriendo sesión. Header `Authorization: Bearer <access>`;
/// body opcional `{name}`. → `{ok, token, user}`.
pub(crate) async fn auth_cloud(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<CloudLoginReq>>,
) -> Response {
    let Some(token) = auth::bearer(&headers) else {
        return (
            StatusCode::UNAUTHORIZED,
            Json(json!({ "ok": false, "error": "falta Authorization: Bearer" })),
        )
            .into_response();
    };
    let user_agent = devices::user_agent_of(&headers).to_string();
    open_cloud_session(&st, &token, body.map(|value| value.0), None, &user_agent).await
}

/// Shared implementation for ordinary Cloud login and the shell courier.  Keeping the JWT gate,
/// membership check and local user linking in one function ensures the courier cannot create a
/// more privileged path than `POST /api/auth/cloud`.
pub(crate) async fn open_cloud_session(
    st: &AppState,
    token: &str,
    body: Option<CloudLoginReq>,
    cloud_tokens: Option<Value>,
    // The `User-Agent` of the login request: the name a device this hub has never seen is born with
    // (hub#494). It has to travel from the handler because this function sees no headers, and there
    // is nothing else in the request that says anything about the **device** — ADR-0257 made the id
    // opaque, and `name` in the body is the person.
    user_agent: &str,
) -> Response {
    let Some(pem) = st.config.jwt_public_key.as_deref() else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "ok": false, "error": "login cloud no disponible (sin clave pública)" })),
        )
            .into_response();
    };
    let claims = match cloud_client::verify_user_jwt(&token, pem) {
        Ok(c) => c,
        Err(e) => {
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({ "ok": false, "error": format!("token inválido: {e}") })),
            )
                .into_response()
        }
    };
    let hub_id = st.hub_id();
    let cloud_user_id = claims.user_id_str();
    let device_id = body.as_ref().and_then(|b| b.device_id.clone());
    let email = body.as_ref().and_then(|b| b.email.clone());
    let name = body
        .as_ref()
        .and_then(|b| b.name.clone())
        .unwrap_or_else(|| format!("user:{cloud_user_id}"));
    // Rol LOCAL por defecto al provisionar un miembro nuevo que aún no tiene `hub_user` (ADR-0157
    // §6: los roles operativos del Hub son locales/custom, ortogonales al rol SaaS). Se elige el
    // rol de **mínimo privilegio** (`employee`), NO `admin` a ciegas: el auto-admin era el hueco
    // que este ADR cierra. Configurable por entorno (`HUB_DEFAULT_ROLE`).
    let base_role = std::env::var("HUB_DEFAULT_ROLE").unwrap_or_else(|_| "employee".into());
    // …unless the SaaS says this user is owner/admin OF THE HUB they are entering (ADR-0201:
    // membership is per hub). That fact already travelled in the token and the Hub threw it away, so
    // an account admin walked into their own hub as an `employee`, unable to import a blueprint or
    // to promote themselves: only the email seeded at deploy time had privilege. See
    // `local_role_for_cloud_login`: only owner/admin rise, and only to `admin`.
    //
    // The role travels in TWO shapes for as long as the transition lasts (hub#350): the new key
    // `hubs[].role` and the legacy mirror `organizations[].role` (× `hubs[].org`). Both are read —
    // that is what lets the SaaS retire the mirror (saas#1177) without dropping anybody's role —
    // and when they disagree the least privileged one wins (see `role_floor_for_cloud_login`).
    let cloud_roles = claims.role_keys_for_hub(&hub_id);
    let default_role = crate::auth::local_role_for_cloud_login(&cloud_roles, &base_role);
    // El mismo rol de cuenta es además un **SUELO reevaluado en CADA login** (paso 2b regla C,
    // hub#347), no solo el rol con el que se provisiona la fila nueva. Antes el rol local era una
    // foto del primer login —`get_or_link_cloud_user` devolvía la fila intacta— y ascender a
    // alguien en el SaaS no llegaba nunca al hub. El suelo solo SUBE: no baja el rol local (quitar
    // el acceso es desactivar el `hub_user`, regla D, no degradarlo en silencio) y no concede
    // `owner` (la propiedad sale de `HUB_OWNER_EMAIL`, ADR-0157).
    let role_floor = crate::auth::role_floor_for_cloud_login(&cloud_roles);
    // **Owner sembrado del env, NO «primer login = owner»** (ADR-0157, corrección de Ioan): el owner
    // es el CREADOR del hub, sembrado por el provisioning del SaaS (`HUB_OWNER_EMAIL`) ANTES del
    // primer login (ver `serve()`). El **enlace** del login con ese owner (y con cualquier usuario
    // **invitado** por el admin) se hace por **email**: `get_or_link_cloud_user` resuelve primero por
    // `cloud_user_id`, luego por email (fila pre-provisionada sin `cloud_user_id`, conservando su
    // rol), y solo si no hay coincidencia crea una fila con el rol de mínimo privilegio. Preferimos
    // el email del **token** (autenticado) sobre el del body (cliente).
    let login_email = if !claims.email.trim().is_empty() {
        Some(claims.email.clone())
    } else {
        email.clone()
    };
    let rt = st.runtime.read().await;
    // ── Gate de presencia (ADR-0157 §5) + regla D (hub#348) ──────────────────────────────────
    // La autenticación (¿es un JWT válido del SaaS?) NO implica autorización (¿pertenece a ESTE
    // hub?). El token lleva el claim *coarse* `hubs: [{id, org}]` y el Hub solo deja entrar si el
    // `hub_id` de esta máquina figura ahí. Eso cerró el auto-admin (cualquier JWT válido quedaba
    // admin local); un token sin el claim (SaaS legacy) trae `hubs` vacío → no es miembro.
    //
    // Rechazar el login era solo la mitad: al miembro revocado le quedaban intactas la sesión ya
    // abierta (TTL 30 días), el PIN y su sitio en el pinpad, así que seguía trabajando como si
    // nada. La otra mitad —regla D— es **cerrar el `hub_user`**: desactivarlo cae de una vez sobre
    // todas esas puertas. Se hace ANTES de responder y con el mismo token autenticado que prueba
    // la revocación.
    if !claims.is_member_of_hub(&hub_id) {
        if let Err(e) = rt
            .revoke_cloud_access(&cloud_user_id, login_email.as_deref())
            .await
        {
            // El cierre local falló, pero el rechazo no se negocia: se registra y se sigue.
            tracing::error!(error = %e, "rule D: could not deactivate the revoked hub_user");
        }
        return (
            StatusCode::FORBIDDEN,
            Json(json!({
                "ok": false,
                "error": "you are not a member of this hub: ask an administrator for an invitation",
                "code": "not_a_member",
            })),
        )
            .into_response();
    }
    match rt
        .get_or_link_cloud_user(
            &cloud_user_id,
            &name,
            &default_role,
            login_email.as_deref(),
            role_floor,
        )
        .await
    {
        Ok(user) => {
            // Si es el primer login, siembra el correo Cloud en el perfil local. Una vez existe,
            // NO se sobreescribe: las ediciones de `/profile` pertenecen al usuario.
            if let Some(email) = email.filter(|s| !s.trim().is_empty()) {
                if let Ok(profile) = rt.user_profile(&user.id).await {
                    if profile.email.is_empty() {
                        let _ = rt
                            .update_user_profile(
                                &user.id,
                                &erplora_runtime::user_profile::UpdateUserProfile {
                                    first_name: profile.first_name,
                                    last_name: profile.last_name,
                                    email,
                                    preferences: profile.preferences,
                                },
                            )
                            .await;
                    }
                }
            }
            // Device-trust (§2.9): este es un login ONLINE correcto → marca el dispositivo de
            // confianza para habilitar luego el login local por PIN. Best-effort (no bloquea el
            // login si falla el marcado).
            // El nombre por defecto (hub#494) sale del **User-Agent**, y solo cuenta si el hub no
            // conocía ya el dispositivo: `trust_device_with_default_name` lo escribe únicamente en
            // el INSERT. `name` —la persona— sigue yendo a `label`, que es lo que es: una pista de
            // quién entró la última vez, no el nombre de la tablet.
            if let Some(device_id) = device_id.as_deref() {
                let default_name = devices::default_device_name(user_agent);
                let _ = rt
                    .trust_device_with_default_name(device_id, &name, &default_name)
                    .await;
            }
            // Límite de dispositivos del plan (ADR-0154), como en el login por PIN.
            let max_devices = st.entitlement.read().map(|g| g.max_devices()).unwrap_or(0);
            mint_session_with_extra(
                &rt,
                user,
                device_id.as_deref(),
                max_devices,
                &erplora_runtime::identity::Credential::cloud(),
                cloud_tokens,
            )
            .await
        }
        // Puerta cerrada POR EL HUB (regla D, hub#348): el `hub_user` está desactivado y la
        // membresía no lo reabre. Es un rechazo de acceso, no un conflicto de estado, así que sale
        // como `403` con el mismo formato plano que `not_a_member` —el que ya lee el shell— en vez
        // del `409` genérico de un error de dominio.
        Err(erplora_runtime::RuntimeError::Domain { code, message })
            if code == erplora_runtime::identity::DEACTIVATED_ERROR_CODE =>
        {
            (
                StatusCode::FORBIDDEN,
                Json(json!({ "ok": false, "error": message, "code": code })),
            )
                .into_response()
        }
        Err(e) => err_response(e),
    }
}

#[derive(serde::Deserialize)]
pub(crate) struct CourierReq {
    code: String,
    #[serde(default)]
    device_id: Option<String>,
}

#[derive(serde::Deserialize)]
pub(crate) struct CourierGrantUser {
    id: String,
    name: String,
    email: String,
}

#[derive(serde::Deserialize)]
pub(crate) struct CourierGrant {
    access: String,
    refresh: String,
    user: CourierGrantUser,
}

/// Boot courier for the native shell.  The browser submits only the opaque code to its same-origin
/// runtime.  The runtime redeems it server-to-server with its machine credential, then feeds the
/// access JWT through the exact same `/api/auth/cloud` implementation.  JWTs never appear in a URL.
// `HeaderMap` va antes del `Json` a propósito: el extractor del cuerpo consume la petición y tiene
// que ser el último. Lo necesita el nombre por defecto del dispositivo (hub#494): esta puerta abre
// sesión igual que `/api/auth/cloud`, así que un login por el shell nativo no puede dejar la tablet
// sin nombre solo por haber entrado por aquí.
pub(crate) async fn auth_courier(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<CourierReq>,
) -> Response {
    let code = req.code.trim();
    if code.is_empty() || code.len() > 128 {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": "código courier inválido" })),
        )
            .into_response();
    }
    let Some(machine_auth) = auth::machine_auth(&st) else {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({ "ok": false, "error": "hub sin credencial de máquina" })),
        )
            .into_response();
    };
    let cloud = cloud_client::CloudClient::new(&st.config.cloud_base_url);
    let prepared = cloud.session_courier(&machine_auth);
    let mut upstream = st.http.post(&prepared.url).json(&json!({ "code": code }));
    for (name, value) in prepared.headers {
        upstream = upstream.header(name, value);
    }
    let response = match upstream.send().await {
        Ok(response) => response,
        Err(error) => {
            return (
                StatusCode::BAD_GATEWAY,
                Json(json!({ "ok": false, "error": format!("courier no disponible: {error}") })),
            )
                .into_response()
        }
    };
    if !response.status().is_success() {
        let status = if response.status().as_u16() == 400 {
            StatusCode::BAD_REQUEST
        } else {
            StatusCode::BAD_GATEWAY
        };
        return (
            status,
            Json(json!({ "ok": false, "error": "código courier inválido o caducado" })),
        )
            .into_response();
    }
    let grant = match response.json::<CourierGrant>().await {
        Ok(grant) if !grant.access.is_empty() && !grant.refresh.is_empty() => grant,
        _ => {
            return (
                StatusCode::BAD_GATEWAY,
                Json(json!({ "ok": false, "error": "respuesta courier inválida" })),
            )
                .into_response()
        }
    };
    let cloud_tokens = json!({
        "access": grant.access,
        "refresh": grant.refresh,
        "cloud_user": {
            "id": grant.user.id,
            "name": grant.user.name,
            "email": grant.user.email,
        }
    });
    let access = cloud_tokens["access"]
        .as_str()
        .unwrap_or_default()
        .to_string();
    let login = CloudLoginReq {
        name: cloud_tokens["cloud_user"]["name"]
            .as_str()
            .map(str::to_string),
        email: cloud_tokens["cloud_user"]["email"]
            .as_str()
            .map(str::to_string),
        device_id: req.device_id,
    };
    open_cloud_session(
        &st,
        &access,
        Some(login),
        Some(cloud_tokens),
        devices::user_agent_of(&headers),
    )
    .await
}

#[derive(serde::Deserialize)]
pub(crate) struct SetPinReq {
    pin: String,
}

/// Fija el PIN del **usuario de la sesión actual** (`X-Hub-Session`). Lo usa el alta de PIN tras el
/// primer login cloud (§2.9): el usuario ya está autenticado por su JWT→sesión y elige su PIN en
/// este dispositivo de confianza. Body `{pin}` (4 dígitos; vacío lo borra). → `{ok}` (401 sin sesión).
pub(crate) async fn auth_set_pin(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<SetPinReq>,
) -> Response {
    let rt = st.runtime.read().await;
    let Some(token) = auth::session_token(&headers) else {
        return unauthorized(auth::AuthError::MissingSession);
    };
    let user = match rt.resolve_session(&token).await {
        Ok(Some(u)) => u,
        Ok(None) => {
            return unauthorized(auth::AuthError::Invalid(
                "sesión inválida o caducada".into(),
            ))
        }
        Err(e) => return err_response(e),
    };
    match rt.set_pin(&user.id, &req.pin).await {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(e) => err_response(e),
    }
}

/// Cierra la sesión del header `X-Hub-Session` (logout).
pub(crate) async fn auth_logout(State(st): State<AppState>, headers: HeaderMap) -> Response {
    if let Some(token) = auth::session_token(&headers) {
        let rt = st.runtime.read().await;
        let _ = rt.delete_session(&token).await;
    }
    Json(json!({ "ok": true })).into_response()
}

/// Abre una sesión para `user` y devuelve `{ok, token, user}`.
///
/// `device_id` = identidad del dispositivo del login (o `None`); `max_devices` = límite del plan
/// (ADR-0154), leído del estado de entitlement del server. Con `max_devices == 1` y `device_id`
/// presente se aplica *single active device session*: se desalojan las sesiones de otros
/// dispositivos ANTES de abrir la nueva (takeover; la sesión desalojada da 401 en su siguiente
/// petición al no resolver). `0` = ilimitado / sin `device_id` = comportamiento actual.
pub(crate) async fn mint_session(
    rt: &erplora_runtime::Runtime,
    user: erplora_runtime::identity::HubUser,
    device_id: Option<&str>,
    max_devices: u32,
    credential: &erplora_runtime::identity::Credential,
) -> Response {
    mint_session_with_extra(rt, user, device_id, max_devices, credential, None).await
}

pub(crate) async fn mint_session_with_extra(
    rt: &erplora_runtime::Runtime,
    user: erplora_runtime::identity::HubUser,
    device_id: Option<&str>,
    max_devices: u32,
    // **Con qué se probó la identidad** (hub#658). Viaja hasta la fila de `hub_session` porque el
    // login es la mitad de la traza que contesta «alguien usó mi tarjeta»; la otra mitad la escribe
    // `_elevation_audit`.
    credential: &erplora_runtime::identity::Credential,
    extra: Option<Value>,
) -> Response {
    if let Err(e) = rt.enforce_device_limit(max_devices, device_id).await {
        return err_response(e);
    }
    // Cuánto vive la sesión lo decide el MODO DEL DISPOSITIVO (hub#358), no una constante global:
    // un mostrador caduca dentro del turno que abrió y el equipo propio conserva la sesión larga.
    // Sin `device_id` (cliente que no dice cuál es) sale la **corta** — la misma dirección
    // fail-closed que el propio modo: no identificarse nunca compra la sesión larga.
    let ttl_secs = match rt
        .session_ttl_for_device(device_id.unwrap_or_default())
        .await
    {
        Ok(ttl) => ttl,
        Err(e) => return err_response(e),
    };
    match rt
        .create_session_with_credential(&user.id, ttl_secs, device_id, credential)
        .await
    {
        Ok(token) => {
            let permissions = rt.session_permissions(&user.role);
            let mut payload = json!({
                "ok": true,
                "token": token,
                "user": user,
                "permissions": permissions,
            });
            if let (Some(target), Some(source)) = (
                payload.as_object_mut(),
                extra.and_then(|value| value.as_object().cloned()),
            ) {
                target.extend(source);
            }
            Json(payload).into_response()
        }
        Err(e) => err_response(e),
    }
}
