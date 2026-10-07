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
pub(crate) async fn auth_pin(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<PinReq>,
) -> Response {
    // Per-address guard (hub#2282): first and cheapest, before the device gate and the database.
    let client = crate::address_guard::client_address(&headers);
    if let Some(retry_after_secs) = client
        .as_deref()
        .and_then(|c| st.address_guard.locked_for(c))
    {
        return too_many_attempts(retry_after_secs);
    }
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
                &st.stream_limiter,
                user,
                device_id,
                max_devices,
                &erplora_runtime::identity::Credential::pin(),
            )
            .await
        }
        Ok(None) => {
            st.login_throttle.record_failure(&req.name);
            crate::address_guard::record_guess(
                &st,
                client.as_deref(),
                crate::address_guard::Failure::Pin,
            );
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

/// Whether this caller may learn WHO works here — the faces of the pinpad that the boot context
/// carries (hub#2510). They exist for the pinpad, and the pinpad only opens on a device the PIN
/// door would let through, so the question is asked in the order that door asks it:
///
/// 1. a **live session** says yes: the approval dialog and «switch user» run behind one, also on a
///    browser that came in through the panel courier and was never trusted (HUB-F131). A session
///    is not stopped by the address lock (HUB-F135: whoever is in keeps working). One that does
///    not resolve counts against the address like at any other door (hub#2282), or this read would
///    be a free oracle for session tokens;
/// 2. a **locked address** says no, before looking at the device — the PIN door's first check;
/// 3. the **device**, by the PIN door's own rule: trust disarmed, trusted, or the first device of a
///    virgin demo ([`device_mode::demo_would_adopt`], shared so the two cannot drift).
///
/// Fail-closed: a lookup that errors withholds; the login screen then offers the account door.
pub(crate) async fn may_name_the_team(
    st: &AppState,
    rt: &erplora_runtime::Runtime,
    headers: &HeaderMap,
) -> bool {
    let client = crate::address_guard::client_address(headers);
    if let Some(token) = auth::session_token(headers) {
        match rt.resolve_session(&token).await {
            Ok(Some(_)) => return true,
            Ok(None) => crate::address_guard::record_rejected_credential(
                st,
                client.as_deref(),
                crate::address_guard::Failure::SessionInvalid,
                &token,
            ),
            Err(error) => {
                tracing::warn!(%error, "hub context: could not resolve the presented session");
                return false;
            }
        }
    }
    if client
        .as_deref()
        .and_then(|c| st.address_guard.locked_for(c))
        .is_some()
    {
        return false;
    }
    if !st.config.device_trust_enforce {
        return true;
    }
    let device_id = device_mode::device_id_of(headers);
    if device_id.is_empty() {
        return false;
    }
    match rt.is_device_trusted(device_id).await {
        Ok(true) => true,
        Ok(false) => device_mode::demo_would_adopt(st.config.demo, rt, device_id)
            .await
            .unwrap_or(false),
        Err(error) => {
            tracing::warn!(%error, "hub context: could not read the device trust");
            false
        }
    }
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
pub(crate) async fn auth_badge(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<BadgeReq>,
) -> Response {
    let client = crate::address_guard::client_address(&headers);
    if let Some(retry_after_secs) = client
        .as_deref()
        .and_then(|c| st.address_guard.locked_for(c))
    {
        return too_many_attempts(retry_after_secs);
    }
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
                &st.stream_limiter,
                matched.user,
                device_id,
                max_devices,
                &erplora_runtime::identity::Credential::badge(&matched.badge_index),
            )
            .await
        }
        Ok(None) => {
            st.login_throttle.record_failure(&throttle_key);
            crate::address_guard::record_guess(
                &st,
                client.as_deref(),
                crate::address_guard::Failure::Badge,
            );
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
            Json(json!({
                "ok": false,
                "error": "missing Authorization: Bearer",
                "code": "cloud_token_missing",
            })),
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
            Json(json!({
                "ok": false,
                "error": "cloud login unavailable: the hub has no SaaS public key",
                "code": "cloud_login_not_configured",
            })),
        )
            .into_response();
    };
    let claims = match cloud_client::verify_user_jwt(&token, pem) {
        Ok(c) => c,
        Err(error) => {
            // The detail goes to the log, never to the answer (hub#2310): `jsonwebtoken` repeats an
            // unknown `alg` verbatim, so the body echoed the caller's own text and gave the screen
            // no code to read. `?` over the text, never `%` or `{e}` (hub#2300), keeps a raw `\n`
            // in that `alg` from ending this line and forging the next one.
            tracing::warn!(
                error = ?error.to_string(),
                "cloud login refused: the user token does not verify"
            );
            return (
                StatusCode::UNAUTHORIZED,
                Json(json!({
                    "ok": false,
                    "error": "the user token does not verify",
                    "code": "cloud_token_invalid",
                })),
            )
                .into_response();
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
                &st.stream_limiter,
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
/// Every refusal carries a stable `code` (hub#2176): the shell reports the code, never the prose,
/// so without it a failed courier reaches the team with no reason attached.
// `HeaderMap` goes before `Json` on purpose: the body extractor consumes the request and must be
// the last one. The default device name needs it (hub#494): this door opens a session exactly like
// `/api/auth/cloud`, so a login through the native shell must not leave the tablet unnamed just
// because it came in this way.
pub(crate) async fn auth_courier(
    State(st): State<AppState>,
    headers: HeaderMap,
    Json(req): Json<CourierReq>,
) -> Response {
    let code = req.code.trim();
    if code.is_empty() || code.len() > 128 {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({ "ok": false, "error": "código courier inválido", "code": "courier_invalid" })),
        )
            .into_response();
    }
    let Some(machine_auth) = auth::machine_auth(&st) else {
        // 424 and not a `5xx` (hub#1763): the shell reads this answer to decide whether to fall
        // back to the login form, and the edge replaces the body of a `5xx` with its own page.
        return (
            crate::cloud_proxy::CLOUD_FAILED,
            Json(json!({
                "ok": false,
                "error": "hub sin credencial de máquina",
                "code": crate::cloud_proxy::HUB_NOT_ENROLLED,
            })),
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
                crate::cloud_proxy::CLOUD_FAILED,
                Json(json!({
                    "ok": false,
                    "error": crate::cloud_proxy::CLOUD_UNREACHABLE,
                    "code": crate::cloud_proxy::cloud_unreachable(&error.to_string()),
                })),
            )
                .into_response()
        }
    };
    if !response.status().is_success() {
        // Only a `400` is about the code itself (the SaaS answers «invalid or expired» without
        // telling the two apart). Anything else refused the HUB — its machine credential — or
        // failed, and the report has to point at that culprit, not at the person's code.
        let (status, code) = if response.status().as_u16() == 400 {
            (StatusCode::BAD_REQUEST, "courier_rejected")
        } else {
            (
                crate::cloud_proxy::CLOUD_FAILED,
                crate::cloud_proxy::CLOUD_REJECTED,
            )
        };
        return (
            status,
            Json(
                json!({ "ok": false, "error": "código courier inválido o caducado", "code": code }),
            ),
        )
            .into_response();
    }
    let grant = match response.json::<CourierGrant>().await {
        Ok(grant) if !grant.access.is_empty() && !grant.refresh.is_empty() => grant,
        _ => {
            return (
                crate::cloud_proxy::CLOUD_FAILED,
                Json(json!({
                    "ok": false,
                    "error": "respuesta courier inválida",
                    "code": crate::cloud_proxy::CLOUD_UNREADABLE,
                })),
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
    /// Requerido si el usuario YA tiene un PIN (hub#1430, «Mi perfil» → cambiar mi PIN); ausente u
    /// omitido en la alta de PIN tras el primer login cloud, donde no hay nada que confirmar.
    #[serde(default)]
    current_pin: Option<String>,
}

/// Fija (o cambia) el PIN del **usuario de la sesión actual** (`X-Hub-Session`). Dos llamadores:
/// la alta de PIN tras el primer login cloud (§2.9, sin `current_pin`) y «Mi perfil» → cambiar mi
/// PIN (hub#1430) — el usuario ya está autenticado por su sesión y elige su PIN en este
/// dispositivo. Body `{pin, current_pin?}` (`pin`: 4/6 dígitos, vacío lo borra; `current_pin`
/// obligatorio si ya hay un PIN, y tiene que coincidir con el de hoy). → `{ok}` (401 sin sesión,
/// 409 si el PIN actual no coincide o el nuevo ya lo tiene otro, 429 `too_many_attempts` con el
/// presupuesto de intentos gastado).
///
/// **Brute-force guard (hub#2499).** PINs are unique (hub#355), so this door has to say «that one
/// is taken» — which, unbraked, let anybody with a session probe numbers until they hit a
/// colleague's, then try it against the names on the pinpad grid. It spends a budget of tries
/// against the PERSON ([`crate::login_throttle::LoginThrottle::pin_change`]: thirty an hour,
/// hub#2564, fewer a day than the pinpad's five every five minutes), and every try counts, the
/// accepted ones too: an
/// accepted number becomes the prober's PIN and they carry on, so counting only refusals would
/// still hand out a taken PIN per refusal. The key is the user id, in a map kept apart from the
/// pinpad's (`pin_change_throttle`, shared with the PIN doors of Empleados, hub#2518): the pinpad's counter is keyed by whatever name the caller types, a
/// successful login clears it, and five wrong PINs under a name lock it — none of which may reach
/// this budget. No per-address guard here: the caller holds a session that resolves, and the
/// person is a key they cannot rotate the way an attacker rotates names.
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
    // Checked BEFORE the runtime looks at the digits: a locked caller gets no taken/free signal.
    if let Some(retry_after_secs) = st.pin_change_throttle.locked_for(&user.id) {
        return too_many_attempts(retry_after_secs);
    }
    st.pin_change_throttle.record_attempt(&user.id);
    match rt
        .set_pin(&user.id, req.current_pin.as_deref(), &req.pin)
        .await
    {
        Ok(()) => Json(json!({ "ok": true })).into_response(),
        Err(e) => err_response(e),
    }
}

/// Cierra la sesión del header `X-Hub-Session` (logout).
pub(crate) async fn auth_logout(State(st): State<AppState>, headers: HeaderMap) -> Response {
    if let Some(token) = auth::session_token(&headers) {
        let rt = st.runtime.read().await;
        let _ = rt.delete_session(&token).await;
        // hub#2522: after the row is gone, so a ticket minted from now on cannot see it alive.
        st.stream_limiter
            .cut(&crate::event_stream::session_tag(&token));
    }
    Json(json!({ "ok": true })).into_response()
}

#[derive(serde::Deserialize, Default)]
pub(crate) struct HandoffReq {
    /// Where to land inside the SaaS. Always an **own route**; see [`handoff_destination`].
    #[serde(default)]
    next: Option<String>,
}

/// Where whoever asks for nothing goes: the panel. It is the door the "manage your business" link opens.
const HANDOFF_DEFAULT_NEXT: &str = "/dashboard/";

/// Percent-encoding of a **whole** query value: only RFC 3986 unreserved characters survive.
/// Unlike the one in `media`, here `/` is escaped too — the destination travels INSIDE a parameter,
/// and leaving it raw slashes is letting it rewrite the route that carries it.
fn pct_encode_strict(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    for b in s.bytes() {
        match b {
            b'A'..=b'Z' | b'a'..=b'z' | b'0'..=b'9' | b'-' | b'_' | b'.' | b'~' => {
                out.push(b as char)
            }
            _ => out.push_str(&format!("%{b:02X}")),
        }
    }
    out
}

/// The requested destination, if it is a route **of the SaaS itself**; `None` if it leaves it.
///
/// The SaaS has its own allow-list when redeeming the code, and this is still checked **here**: a
/// hub that forwards absolute addresses is a hub that would point a freshly opened session at
/// somebody else's site, and refusing early also avoids spending the one-time code on the attempt.
///
/// It must start with `/` and the next character must be neither `/` nor `\`: `//host` is a
/// protocol-relative URL, and so is `/\host` for browsers, which normalise the backslash. That is
/// why `\` is rejected in any position, not only in the second one.
fn handoff_destination(next: Option<&str>) -> Option<String> {
    let next = next.map(str::trim).filter(|n| !n.is_empty());
    let Some(next) = next else {
        return Some(HANDOFF_DEFAULT_NEXT.to_string());
    };
    let mut chars = next.chars();
    if chars.next() != Some('/') {
        return None;
    }
    if matches!(chars.next(), Some('/') | Some('\\')) {
        return None;
    }
    if next.contains('\\') || next.chars().any(|c| c.is_control()) {
        return None;
    }
    Some(next.to_string())
}

/// The pages of the SaaS that are the ACCOUNT of whoever is standing at the till, as opposed to a
/// task of managing the business (hub#1539).
///
/// «Mi perfil» links to the one place where a person changes their own password, their own email
/// and their own second factor. It is not administration — it is theirs by definition — and until
/// this list existed the door asked them for `hub.administer` all the same, so an assistant manager
/// who had typed her email and her password was sent to a login form to reach her own account.
///
/// Deleting that account is just as much hers (hub#2451): «Mi perfil → Borrar mi cuenta» lands on
/// the SaaS's deletion confirmation, the in-app path Google Play demands from an app that lets
/// people sign up.
const HANDOFF_OWN_ACCOUNT: &[&str] = &["/dashboard/profile/", "/dashboard/profile/delete/"];

/// Whether `next` lands on the asker's own account.
///
/// 🔴 **This does not confine the browser, and must not be read as if it did.** The one-time code
/// the SaaS mints opens a full session; `next` only picks the landing page, so whoever lands on the
/// account page can click onwards exactly as if they had signed in by hand — which is precisely the
/// point, because that session grants nothing they could not get by typing that same password. What
/// this decides is narrower: WHERE THIS HUB RELAXES ITS OWN CHECK, so hub#1400's lock keeps
/// applying, untouched, to every management destination.
///
/// The comparison is **exact** on the path, never a prefix: `/dashboard/profile/../billing/` and
/// `/dashboard/profile-of-somebody-else/` both start with the account page and are neither of it.
/// Traversal needs no rule of its own because `..` cannot survive an exact match. The query and the
/// fragment are dropped first — they do not change which page the browser opens, so they may not
/// change the answer.
fn is_own_account_destination(next: &str) -> bool {
    let path = next.split(['?', '#']).next().unwrap_or_default();
    let path = path.strip_suffix('/').unwrap_or(path);
    HANDOFF_OWN_ACCOUNT
        .iter()
        .any(|own| own.strip_suffix('/').unwrap_or(own) == path)
}

/// **`POST /api/auth/handoff`** — hands the browser the SaaS session of whoever is at the till
/// (pm#196, hub#1400). Body `{next?}` → `200 {url}` with a one-time address.
///
/// The till links to erplora.com for what it does not sell (plan, invoices, module checkout).
/// Inside the installed app that link opens in the system browser, which is a **different cookie
/// jar** from the webview: the owner typed her password and second factor again right before
/// paying. This route is the Hub→SaaS half of the one-time email ADR-0157 §8 already has in the
/// opposite direction.
///
/// **Why it goes through the runtime** when the browser already holds the JWT and could ask for it
/// itself: because the SaaS cannot see what is checked here. Whether the person standing there
/// proved who they are with **their password** or with a **shift PIN** is something only
/// `hub_session.credential_kind` says (hub#658). The lock (hub#1400) is that only the first one
/// carries off a browser session: a PIN is short, memorable and typed in front of people (ADR-0226
/// — the local user's credential is never administrative), and turning it into the key to the
/// billing panel would hand the business's money to whoever opens the till.
///
/// That is why `hub.administer` (ADR-0248) is **not sufficient**: it is a permission of the ROLE
/// and the question is about the METHOD. The third check closes the gap the other two leave — the
/// presented JWT has to name the same person as the session, because a till nobody has signed out
/// of keeps the previous person's tokens in `localStorage`.
///
/// Nor is it **necessary for every destination** (hub#1539). It answers «is this task yours?», and
/// the account page of the person standing there is theirs by definition: see
/// [`is_own_account_destination`], which is why the destination is settled before the permission.
///
/// Every refusal travels as its CODE, never as its prose (ADR-0055).
pub(crate) async fn auth_handoff(
    State(st): State<AppState>,
    headers: HeaderMap,
    body: Option<Json<HandoffReq>>,
) -> Response {
    fn refuse(status: StatusCode, code: &str) -> Response {
        (status, Json(json!({ "ok": false, "code": code }))).into_response()
    }

    let Some(session) = auth::session_token(&headers) else {
        return refuse(StatusCode::UNAUTHORIZED, "handoff_session_required");
    };
    let (user, credential, administers) = {
        let rt = st.runtime.read().await;
        match rt.resolve_session_with_credential(&session).await {
            Ok(Some((user, credential))) => {
                let administers = rt
                    .session_permissions(&user.role)
                    .contains(erplora_runtime::hub_users::ADMINISTER_PERMISSION);
                (user, credential, administers)
            }
            Ok(None) => return refuse(StatusCode::UNAUTHORIZED, "handoff_session_required"),
            Err(e) => {
                tracing::error!(error = ?e.to_string(), "handoff: could not resolve the session");
                return refuse(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "handoff_session_unreadable",
                );
            }
        }
    };

    if credential.kind != erplora_runtime::identity::CREDENTIAL_CLOUD {
        return refuse(StatusCode::FORBIDDEN, "handoff_requires_cloud_login");
    }
    // The destination is resolved BEFORE the permission, because it is what decides which
    // permission applies: management is somebody's task, one's own account is not (hub#1539).
    let Some(next) = handoff_destination(body.and_then(|b| b.0.next).as_deref()) else {
        return refuse(StatusCode::BAD_REQUEST, "handoff_destination_not_allowed");
    };
    if !administers && !is_own_account_destination(&next) {
        return refuse(StatusCode::FORBIDDEN, "handoff_requires_administer");
    }

    let Some(access) = auth::bearer(&headers) else {
        return refuse(StatusCode::UNAUTHORIZED, "handoff_user_token_required");
    };
    let Some(pem) = st.config.jwt_public_key.as_deref() else {
        // Without the public key the hub cannot check who the token names, and this door exists
        // precisely to check it. It says so; it does not open halfway.
        tracing::error!("handoff: the hub has no SaaS public key, the door stays shut");
        return refuse(StatusCode::SERVICE_UNAVAILABLE, "handoff_not_configured");
    };
    let claims = match cloud_client::verify_user_jwt(&access, pem) {
        Ok(claims) => claims,
        Err(error) => {
            // `?` over the text and never `%` or `{e}` (hub#2300): `jsonwebtoken` repeats an
            // unknown `alg` verbatim, so a raw `\n` in the caller's token used to end this line and
            // start one that read as `event=auth_failed … client=<another shop>`. `Debug` of the
            // string quotes it and escapes every control character, so it stays one field.
            tracing::warn!(
                error = ?error.to_string(),
                "handoff refused: the user token does not verify"
            );
            return refuse(StatusCode::UNAUTHORIZED, "handoff_user_token_invalid");
        }
    };
    if user.cloud_user_id.as_deref() != Some(claims.user_id_str().as_str()) {
        return refuse(StatusCode::FORBIDDEN, "handoff_identity_mismatch");
    }

    let auth = cloud_client::Auth::UserJwt {
        hub_id: auth::hub_id(&headers, &st.hub_id()),
        access,
    };
    let prepared =
        cloud_client::CloudClient::new(&st.config.cloud_base_url).browser_handoff_issue(&auth);
    let mut request = st.http.post(&prepared.url).json(&json!({}));
    for (name, value) in prepared.headers {
        request = request.header(name, value);
    }
    let code = match request.send().await {
        Ok(response) if response.status().is_success() => match response.json::<Value>().await {
            Ok(body) => match body.get("code").and_then(Value::as_str) {
                Some(code) if !code.is_empty() => code.to_string(),
                _ => {
                    tracing::warn!("handoff: the SaaS answered without a one-time code");
                    return refuse(crate::cloud_proxy::CLOUD_FAILED, "handoff_unavailable");
                }
            },
            Err(e) => {
                tracing::warn!(error = ?e.to_string(), "handoff: unreadable answer from the SaaS");
                return refuse(crate::cloud_proxy::CLOUD_FAILED, "handoff_unavailable");
            }
        },
        Ok(response) => {
            tracing::warn!(
                status = response.status().as_u16(),
                "handoff: the SaaS refused the pass"
            );
            return refuse(crate::cloud_proxy::CLOUD_FAILED, "handoff_unavailable");
        }
        Err(e) => {
            tracing::warn!(error = ?e.to_string(), "handoff: could not ask the SaaS for the pass");
            return refuse(crate::cloud_proxy::CLOUD_FAILED, "handoff_unavailable");
        }
    };

    // The runtime builds the address with ITS idea of where the SaaS is: a page that could pick
    // the host would be picking where the code gets spent. And the one-time code is the whole
    // credential that travels — neither the Bearer nor the machine token goes with it.
    let url = format!(
        "{}/auth/handoff/{}/?next={}",
        st.config.cloud_base_url.trim_end_matches('/'),
        pct_encode_strict(&code),
        pct_encode_strict(&next),
    );
    Json(json!({ "ok": true, "url": url })).into_response()
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
    stream_limiter: &crate::event_stream::StreamLimiter,
    user: erplora_runtime::identity::HubUser,
    device_id: Option<&str>,
    max_devices: u32,
    credential: &erplora_runtime::identity::Credential,
) -> Response {
    mint_session_with_extra(
        rt,
        stream_limiter,
        user,
        device_id,
        max_devices,
        credential,
        None,
    )
    .await
}

pub(crate) async fn mint_session_with_extra(
    rt: &erplora_runtime::Runtime,
    // hub#2571: the live channels of the sessions the device limit throws out close with them.
    stream_limiter: &crate::event_stream::StreamLimiter,
    user: erplora_runtime::identity::HubUser,
    device_id: Option<&str>,
    max_devices: u32,
    // **Con qué se probó la identidad** (hub#658). Viaja hasta la fila de `hub_session` porque el
    // login es la mitad de la traza que contesta «alguien usó mi tarjeta»; la otra mitad la escribe
    // `_elevation_audit`.
    credential: &erplora_runtime::identity::Credential,
    extra: Option<Value>,
) -> Response {
    match rt.enforce_device_limit(max_devices, device_id).await {
        Ok(evicted) => {
            for token in evicted {
                stream_limiter.cut(&crate::event_stream::session_tag(&token));
            }
        }
        Err(e) => return err_response(e),
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
                // **What whoever signs in just proved their identity with** (hub#1400). The shell
                // cannot ask for it afterwards —no route tells it— and needs it before painting:
                // the door to erplora.com is offered only to a password login, and an entry that is
                // shown and then refused is worse than one never shown. It travels from here
                // because the five paths that open a session go through this function; the sixth
                // inherits it.
                "credential_kind": credential.kind,
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

#[cfg(test)]
mod tests {
    use super::*;

    /// Public half of a throwaway pair: the forged token is refused while its header is parsed,
    /// so the key only has to be a valid RSA PEM.
    const HANDOFF_PUB: &str = "-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA8xsyMiSRgmfQusugZuaw
0g+qMj5urzS2z9VxNybCHbWcfMkQaX6Jo7ILZeQTYsVYKhQMbbOZu6HSdQN4tqCn
QarFStcBfo6VWhH/DuvrbPvLN47vAGQslEjYwqkVDm1AvY4zgluVUlkp1LGXRjV1
O1E1jrW7zsasviHRRNAznmsx/otkkkPlleLt+65YnRodBh2ErJ20Hh0cl2eIsmMQ
n0A5ahgGAj6dxgrxHa2vk4mV5iXyJe2rPP3E6gWN8DrrHMAou6Rixjg0Mh/EGsDU
oac71BzarU6Of6OA1U1n949C1CQwpZbMJDCETF/ZvTPQ4b6q+qg/XXovo7kfFsMh
nQIDAQAB
-----END PUBLIC KEY-----
";

    /// The line the address guard writes when a PIN fails — the one the edge ban and the
    /// `erp-hub-auth-failed-burst` alert count — pointing at somebody else's shop.
    const FORGED: &str =
        "WARN erplora_server::address_guard: event=auth_failed reason=pin client=203.0.113.7 hub=h";

    /// Asks for the pass to erplora.com through the real door, as an owner signed in with their
    /// password, presenting a user token whose JWT header names the algorithm `alg`.
    /// `jsonwebtoken` refuses an unknown `alg` with a serde error that repeats the value
    /// verbatim — text the caller controls. Returns the status plus what reached the log.
    async fn logged_handoff(alg: &str) -> (StatusCode, String) {
        use base64::Engine as _;
        let db = erplora_db::testutil::fresh_db().await;
        let rt = erplora_runtime::Runtime::with_hub_id(Box::new(db), "hub-handoff-log");
        rt.ensure_system_tables().await.unwrap();
        let owner = rt
            .create_user("Ana", "4729", "owner", Some("77"))
            .await
            .unwrap();
        let session = rt
            .create_session_with_credential(
                &owner,
                3600,
                Some("till-1"),
                &erplora_runtime::identity::Credential::cloud(),
            )
            .await
            .unwrap();
        let temp = std::env::temp_dir().join(format!("erplora-handoff-log-{}", std::process::id()));
        let cfg = crate::HubConfig {
            demo: false,
            hub_id: "hub-handoff-log".into(),
            cloud_base_url: "http://127.0.0.1:1".into(),
            module_cache: temp.join("modules-cache"),
            auth_mode: crate::state::AuthMode::Session,
            jwt_public_key: Some(HANDOFF_PUB.into()),
            cloud_api_token: None,
            device_trust_enforce: false,
            media_dir: temp,
            sector: None,
            dev_mode: false,
            dev_modules_dir: None,
            module_trusted_keys: Vec::new(),
        };
        let st = crate::AppState::with_config(rt, cfg);

        let b64 = base64::engine::general_purpose::URL_SAFE_NO_PAD;
        let header = b64.encode(json!({ "alg": alg, "typ": "JWT" }).to_string());
        let token = format!("{header}.{}.{}", b64.encode("{}"), b64.encode("sig"));
        let mut headers = HeaderMap::new();
        headers.insert("x-hub-session", session.parse().unwrap());
        headers.insert("authorization", format!("Bearer {token}").parse().unwrap());

        let (sink, guard) = crate::log_capture::capture_scope();
        let response = auth_handoff(State(st), headers, None).await;
        drop(guard);
        // The session lookup inside the door leaves its own `sqlx` DEBUG lines; they are not the
        // refusal and a forged line cannot pass for one (it would carry no timestamp).
        let log = sink
            .text()
            .lines()
            .filter(|line| !line.contains(" DEBUG sqlx::"))
            .map(|line| format!("{line}\n"))
            .collect();
        (response.status(), log)
    }

    #[tokio::test]
    async fn hub2300_a_newline_in_the_user_token_cannot_forge_a_log_line() {
        // A signed-in employee used to end the refusal's line with a raw `\n` smuggled in the
        // token's `alg`, and start a second one that read exactly like a failed PIN elsewhere.
        let (status, log) = logged_handoff(&format!("x\n{FORGED}")).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
        let lines: Vec<&str> = log.lines().collect();
        assert_eq!(
            lines.len(),
            1,
            "one refused handoff must be one line, got {log:?}"
        );
        assert!(
            lines[0].contains("handoff refused: the user token does not verify"),
            "the only line is not the refusal's: {log:?}"
        );
    }

    #[tokio::test]
    async fn hub2300_a_forged_event_stays_quoted_inside_the_error_field() {
        // Without a newline the fake text rode as bare `event=… client=…` pairs, which a
        // key=value reader cannot tell from the hub's own. Quoted, it is one value.
        let (_, log) = logged_handoff(&format!("x {FORGED}")).await;
        let line = log.lines().next().unwrap_or_default();
        let (_, error) = line
            .split_once(" error=\"")
            .unwrap_or_else(|| panic!("the error is not a quoted field: {log:?}"));
        assert!(
            error.ends_with('"') && error.contains(FORGED),
            "the forged text is not enclosed in the error field: {log:?}"
        );
    }

    /// A hub with (or without) the SaaS public key, for the ordinary sign-in with an erplora.com
    /// account. Nothing reaches the network: every case here is refused before the SaaS is asked.
    async fn cloud_login_state(jwt_public_key: Option<&str>) -> crate::AppState {
        let db = erplora_db::testutil::fresh_db().await;
        let rt = erplora_runtime::Runtime::with_hub_id(Box::new(db), "hub-cloud-login");
        rt.ensure_system_tables().await.unwrap();
        let temp = std::env::temp_dir().join(format!("erplora-cloud-login-{}", std::process::id()));
        let cfg = crate::HubConfig {
            demo: false,
            hub_id: "hub-cloud-login".into(),
            cloud_base_url: "http://127.0.0.1:1".into(),
            module_cache: temp.join("modules-cache"),
            auth_mode: crate::state::AuthMode::Session,
            jwt_public_key: jwt_public_key.map(str::to_string),
            cloud_api_token: None,
            device_trust_enforce: false,
            media_dir: temp,
            sector: None,
            dev_mode: false,
            dev_modules_dir: None,
            module_trusted_keys: Vec::new(),
        };
        crate::AppState::with_config(rt, cfg)
    }

    /// Signs in through `POST /api/auth/cloud` with a user token whose JWT header names the
    /// algorithm `alg` — the text `jsonwebtoken` repeats verbatim when it refuses it. Returns the
    /// status, the JSON body and what reached the log.
    async fn cloud_login_with_alg(alg: &str) -> (StatusCode, Value, String) {
        use base64::Engine as _;
        let b64 = base64::engine::general_purpose::URL_SAFE_NO_PAD;
        let header = b64.encode(json!({ "alg": alg, "typ": "JWT" }).to_string());
        let token = format!("{header}.{}.{}", b64.encode("{}"), b64.encode("sig"));
        let mut headers = HeaderMap::new();
        headers.insert("authorization", format!("Bearer {token}").parse().unwrap());
        let st = cloud_login_state(Some(HANDOFF_PUB)).await;
        let (sink, guard) = crate::log_capture::capture_scope();
        let response = auth_cloud(State(st), headers, None).await;
        drop(guard);
        let log = sink
            .text()
            .lines()
            .filter(|line| !line.contains(" DEBUG sqlx::"))
            .map(|line| format!("{line}\n"))
            .collect();
        let status = response.status();
        (status, body_json(response).await, log)
    }

    async fn body_json(response: Response) -> Value {
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }

    #[tokio::test]
    async fn hub2310_a_refused_cloud_token_answers_a_stable_code_and_not_the_callers_text() {
        // The body used to be `token inválido: <jsonwebtoken error>`: no code for the screen to
        // read, and the caller's own `alg` echoed back inside it.
        let (status, body, _) = cloud_login_with_alg(&format!("x {FORGED}")).await;
        assert_eq!(status, StatusCode::UNAUTHORIZED);
        assert_eq!(body["ok"], json!(false));
        assert_eq!(body["code"], json!("cloud_token_invalid"), "{body}");
        assert!(
            !body.to_string().contains("event=auth_failed"),
            "the caller's text came back in the answer: {body}"
        );
    }

    #[tokio::test]
    async fn hub2310_the_refused_cloud_token_is_logged_once_with_its_detail_quoted() {
        // The detail leaves the answer but not the hub: it goes to the log, as one quoted field
        // that a raw `\n` in the caller's `alg` cannot split into a second, forged line.
        let (_, _, log) = cloud_login_with_alg(&format!("x\n{FORGED}")).await;
        let lines: Vec<&str> = log.lines().collect();
        assert_eq!(
            lines.len(),
            1,
            "one refused sign-in must be one line: {log:?}"
        );
        assert!(
            lines[0].contains("cloud login refused: the user token does not verify"),
            "the only line is not the refusal's: {log:?}"
        );
        // A refused sign-in is something an operator looks for; below the production filter it
        // would never be written at all.
        assert!(
            lines[0].contains(" WARN erplora_server::auth_api:"),
            "the refusal is not logged as a warning: {log:?}"
        );
        let (_, error) = lines[0]
            .split_once(" error=\"")
            .unwrap_or_else(|| panic!("the error is not a quoted field: {log:?}"));
        assert!(
            error.ends_with('"') && error.contains(FORGED),
            "the detail is not enclosed in the error field: {log:?}"
        );
    }

    #[tokio::test]
    async fn hub2310_a_hub_without_the_saas_key_answers_a_stable_code() {
        let st = cloud_login_state(None).await;
        let mut headers = HeaderMap::new();
        headers.insert("authorization", "Bearer a.b.c".parse().unwrap());
        let response = auth_cloud(State(st), headers, None).await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        let body = body_json(response).await;
        assert_eq!(body["code"], json!("cloud_login_not_configured"), "{body}");
    }

    #[tokio::test]
    async fn hub2310_a_cloud_sign_in_without_a_token_answers_a_stable_code() {
        let st = cloud_login_state(Some(HANDOFF_PUB)).await;
        let response = auth_cloud(State(st), HeaderMap::new(), None).await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let body = body_json(response).await;
        assert_eq!(body["code"], json!("cloud_token_missing"), "{body}");
    }
}
