//! Revalidación híbrida del entitlement de módulos de pago (UX + defensa en profundidad).
//!
//! El enforcement REAL es server-side: el proxy del SaaS corta las llamadas de pago al
//! instante. Este módulo añade la capa local del hub, deliberadamente **laxa**:
//!
//!  1. Un job periódico (default 24h, env `HUB_ENTITLEMENT_REVALIDATE_SECS`) refresca el
//!     entitlement **firmado RS256** del Cloud con la credencial de máquina del hub
//!     (`X-Hub-Token`) y actualiza este estado compartido.
//!  2. Un módulo queda **bloqueado** si:
//!     - (a) el ÚLTIMO refresh EXITOSO no lo incluye en `claims.modules` (verdad del servidor:
//!       revocado/no comprado → inmediato, sea cual sea su tier), O
//!     - (b) es **DE PAGO** (`tier` fuera de los gratuitos `free`/`basic`/`essential`, ADR-0006)
//!       y acumulamos [`MAX_CONSECUTIVE_FAILURES`] fallos seguidos de refresh **Y** ya pasó la
//!       ventana de gracia del último token válido: la de pago (`paid_grace_until`, claim
//!       ADITIVO del SaaS de 5 días, 2026-07-12) si el token la trae, o si no la global
//!       (`grace_until`, 7 días, la del gate de la app) como hasta ahora.
//!  3. Sin ningún refresh exitoso previo (dev/local sin enrolar, hub recién arrancado) NUNCA
//!     se bloquea (fail-open): la autoridad es el SaaS, no este gate.
//!
//! Decisión del fundador: «si el módulo es de pago deja de funcionar» — y SOLO el de pago. Los
//! módulos gratuitos son locales por diseño (offline-first, ADR-0040: sin sync) y siguen
//! funcionando SIEMPRE, incluso con el hub incomunicado más allá de la gracia; el de pago en
//! cambio depende del entitlement que emite el SaaS. Un tier desconocido se trata como de pago
//! (fail-closed solo en la rama (b), ver [`is_paid_tier`]).
//!
//! El gate solo corta `execute_query`/`execute_command` con el error estable
//! `module_entitlement_blocked` (ver `entitlement_blocked_response` en `lib.rs`); **NUNCA**
//! desinstala módulos ni toca datos. El estado se expone de forma aditiva en el proxy
//! `GET /api/entitlement` (bloque `revalidation`) para que la UI pueda pintar
//! «funcionará hasta {fecha}».

use std::sync::{Arc, RwLock};

use axum::response::IntoResponse;
use cloud_client::EntitlementClaims;
use serde_json::Value;

/// Intervalo por defecto del job de revalidación: 24h (override: `HUB_ENTITLEMENT_REVALIDATE_SECS`).
pub const DEFAULT_REVALIDATE_SECS: u64 = 86_400;

/// Nº de fallos CONSECUTIVOS de refresh a partir del cual (junto con la gracia vencida) se
/// bloquean los módulos del último token válido.
pub const MAX_CONSECUTIVE_FAILURES: u32 = 3;

/// Estado de la revalidación periódica. Vive en [`crate::AppState`] tras un `RwLock` (mismo
/// patrón que `MachineToken`): lo escribe el job de background y lo leen los handlers
/// `query`/`command` (gate) y el proxy `/api/entitlement` (UI).
#[derive(Debug, Default)]
pub struct RevalidationState {
    /// Claims del último token **verificado** (firma RS256 OK) traído con éxito del Cloud.
    /// `None` = nunca hubo refresh exitoso → fail-open (no se bloquea nada).
    pub last_claims: Option<EntitlementClaims>,
    /// Unix-ts del último refresh EXITOSO.
    pub last_refresh_ok_at: Option<i64>,
    /// Unix-ts del último INTENTO de refresh (éxito o fallo) — `last_check` para la UI.
    pub last_check_at: Option<i64>,
    /// Fallos consecutivos de refresh; se resetea a 0 en cada éxito.
    pub consecutive_failures: u32,
}

/// Celda compartida del estado (job de background ↔ handlers), como `MachineToken`.
pub type SharedRevalidation = Arc<RwLock<RevalidationState>>;

/// Why a pushed entitlement token was NOT applied (hub#2105).
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum PushRefusal {
    WrongHub,
    Stale,
}

/// Crea la celda compartida vacía (estado inicial fail-open).
pub fn new_shared() -> SharedRevalidation {
    Arc::new(RwLock::new(RevalidationState::default()))
}

/// ¿Es `tier` un módulo DE PAGO? Los tiers gratuitos (ADR-0006: `basic` + `essential`; `free`
/// por robustez) quedan EXENTOS de la rama (b) del bloqueo: los módulos free son locales por
/// diseño (offline-first, ADR-0040) y deben seguir funcionando aunque el hub quede incomunicado.
/// Un tier ausente/desconocido se trata como de pago — fail-closed SOLO en la rama (b), que ya
/// exige `MAX_CONSECUTIVE_FAILURES` fallos consecutivos Y la gracia vencida.
fn is_paid_tier(tier: &str) -> bool {
    !matches!(
        tier.trim().to_ascii_lowercase().as_str(),
        "free" | "basic" | "essential"
    )
}

impl RevalidationState {
    /// Registra un refresh EXITOSO: guarda las claims verificadas y resetea el contador.
    pub fn apply_success(&mut self, claims: EntitlementClaims, now: i64) {
        self.last_claims = Some(claims);
        self.last_refresh_ok_at = Some(now);
        self.last_check_at = Some(now);
        self.consecutive_failures = 0;
    }

    /// Applies a token the SaaS PUSHED to this hub (hub#2105) as if the daily tick had just
    /// fetched it, so a plan change lands at once instead of a day later or after a restart.
    ///
    /// The caller has already verified the signature. What is left is the two checks a valid
    /// signature does not cover: the token names THIS hub, and it is not older than the one in
    /// force — otherwise a captured token from before an upgrade could roll the plan back. The
    /// same `iat` again is accepted (idempotent: a SaaS retry must not read as a failure).
    pub fn apply_pushed(
        &mut self,
        claims: EntitlementClaims,
        hub_id: &str,
        now: i64,
    ) -> Result<(), PushRefusal> {
        if claims.hub_id != hub_id {
            return Err(PushRefusal::WrongHub);
        }
        if self
            .last_claims
            .as_ref()
            .is_some_and(|current| claims.iat < current.iat)
        {
            return Err(PushRefusal::Stale);
        }
        self.apply_success(claims, now);
        Ok(())
    }

    /// Registra un refresh FALLIDO (red/HTTP/firma): incrementa el contador de fallos.
    pub fn apply_failure(&mut self, now: i64) {
        self.last_check_at = Some(now);
        self.consecutive_failures = self.consecutive_failures.saturating_add(1);
    }

    /// Regla de bloqueo por módulo (ver doc del módulo). `now` lo pasa el llamador para
    /// mantener la función pura y testeable sin reloj real (como `verify_entitlement`).
    pub fn is_blocked(&self, module_id: &str, now: i64) -> bool {
        // Sin refresh exitoso previo no hay verdad conocida → fail-open (la autoridad es el SaaS).
        let Some(claims) = &self.last_claims else {
            return false;
        };
        // (a) Verdad del servidor: el último refresh OK no lo incluye (revocado/no comprado)
        // → bloqueado inmediato, sea cual sea su tier (que ni siquiera conocemos).
        let Some(entry) = claims.modules.iter().find(|m| m.module_id == module_id) else {
            return true;
        };
        // (b) Entitled según el último token válido: solo un módulo DE PAGO se bloquea, y solo
        // si llevamos demasiados fallos seguidos Y además venció su ventana de gracia — la DE
        // PAGO (`paid_grace_until`, claim aditivo) si el token la trae; si no, la global
        // (`grace_until`). Los tiers gratuitos siguen funcionando SIEMPRE (offline-first).
        is_paid_tier(&entry.tier)
            && self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES
            && now > claims.paid_grace_until.unwrap_or(claims.grace_until)
    }

    /// `grace_until` del último token válido (para la UI: «funcionará hasta {fecha}»).
    pub fn grace_until(&self) -> Option<i64> {
        self.last_claims.as_ref().map(|c| c.grace_until)
    }

    /// Nº máximo de **dispositivos activos** del plan según el último token válido (ADR-0154).
    /// `0` = ilimitado, y también el default fail-open cuando aún no hubo refresh exitoso (la
    /// autoridad del límite es el SaaS; sin claim conocido, el hub no aplica takeover local).
    /// Lo lee `mint_session` para desalojar sesiones de otros dispositivos al abrir una nueva.
    pub fn max_devices(&self) -> u32 {
        self.last_claims
            .as_ref()
            .map(|c| c.max_devices)
            .unwrap_or(0)
    }

    /// Nº máximo de **usuarios activos** del plan según el último token válido (saas#1953,
    /// ADR-0474): 3 en Gratis. `0` = ilimitado, y también el default fail-open sin refresh exitoso
    /// previo — misma dirección que [`Self::max_devices`]: sin claim conocido el hub no inventa un
    /// tope, porque quien conoce el plan es el SaaS. Lo leen las puertas que dan de alta gente.
    pub fn max_users(&self) -> u32 {
        self.last_claims.as_ref().map(|c| c.max_users).unwrap_or(0)
    }

    /// Cuota de base de datos del plan en GiB según el último token válido (saas#817).
    /// `0` = ilimitado/autoscaling y también el default fail-open para tokens antiguos o cuando
    /// aún no hubo un refresh exitoso.
    pub fn max_database_size_gb(&self) -> u32 {
        self.last_claims
            .as_ref()
            .map(|c| c.max_database_size_gb)
            .unwrap_or(0)
    }

    /// `paid_grace_until` del último token válido: gracia ESPECÍFICA de los módulos de pago
    /// (claim aditivo del SaaS). `None` = el token no la trae → aplica `grace_until`.
    pub fn paid_grace_until(&self) -> Option<i64> {
        self.last_claims.as_ref().and_then(|c| c.paid_grace_until)
    }

    /// Filtra de `installed` los módulos bloqueados a fecha `now` (para el proxy de entitlement).
    pub fn blocked_modules(&self, installed: &[String], now: i64) -> Vec<String> {
        installed
            .iter()
            .filter(|id| self.is_blocked(id, now))
            .cloned()
            .collect()
    }

    /// Bloque JSON **aditivo** `revalidation` que el proxy `/api/entitlement` añade a la
    /// respuesta del Cloud (no rompe el contrato actual; la UI lo consume si está).
    pub fn revalidation_json(&self, installed: &[String], now: i64) -> Value {
        serde_json::json!({
            "blocked_modules": self.blocked_modules(installed, now),
            "grace_until": self.grace_until(),
            "paid_grace_until": self.paid_grace_until(),
            "last_check": self.last_check_at,
            "last_refresh_ok_at": self.last_refresh_ok_at,
            "consecutive_failures": self.consecutive_failures,
        })
    }
}

/// Registra en la celda compartida el resultado de UN tick del job de revalidación.
/// Separado del fetch de red para poder testearlo con estado/clock inyectados.
pub fn record_outcome(
    cell: &SharedRevalidation,
    outcome: Result<EntitlementClaims, String>,
    now: i64,
) {
    // Si el lock está envenenado (panic de otro hilo) se degrada a no-op: este estado es
    // UX/defensa en profundidad, nunca debe tumbar el server.
    let Ok(mut guard) = cell.write() else { return };
    match outcome {
        Ok(claims) => guard.apply_success(claims, now),
        Err(e) => {
            tracing::warn!(error = %e, fallos = guard.consecutive_failures + 1, "revalidación de entitlement fallida");
            guard.apply_failure(now);
        }
    }
}

/// Intervalo del job en segundos: el valor del env `HUB_ENTITLEMENT_REVALIDATE_SECS` si es un
/// entero > 0; si no (ausente, vacío, no numérico o 0), el default de 24h.
pub fn interval_secs(env_value: Option<&str>) -> u64 {
    env_value
        .and_then(|v| v.trim().parse::<u64>().ok())
        .filter(|v| *v > 0)
        .unwrap_or(DEFAULT_REVALIDATE_SECS)
}

/// Baja del Cloud la clave pública + el entitlement firmado (credencial de máquina) y verifica
/// la firma RS256 y la gracia — la MISMA ruta de verificación que el gate de arranque Tauri
/// (`verify_entitlement`). Glue de red del tick: el manejo de resultado (estado/contador) vive
/// en [`record_outcome`], que es lo testeable sin red.
pub async fn fetch_verified_claims(
    http: &reqwest::Client,
    cloud_base_url: &str,
    auth: &cloud_client::Auth,
    now: i64,
) -> Result<EntitlementClaims, String> {
    let cloud = cloud_client::CloudClient::new(cloud_base_url);

    // 1) Clave pública RSA (endpoint público, sin auth).
    #[derive(serde::Deserialize)]
    struct Pk {
        public_key: String,
    }
    let pk_body = exec_get(http, cloud.public_key()).await?;
    let pk: Pk = serde_json::from_str(&pk_body).map_err(|e| format!("public-key: {e}"))?;

    // 2) Entitlement firmado del hub (X-Hub-Token + X-Hub-Id).
    let ent_body = exec_get(http, cloud.entitlement(auth)).await?;
    let ent = cloud_client::EntitlementResponse::parse(&ent_body)
        .map_err(|e| format!("entitlement: {e}"))?;

    // 3) Verificación offline-style: firma RS256 + ventana de gracia.
    cloud_client::verify_entitlement(&ent.token, &pk.public_key, now).map_err(|e| e.to_string())
}

/// `POST /api/entitlement/refresh` — the SaaS hands this hub its new entitlement (hub#2105).
///
/// The body is `{"token": "<RS256 JWT>"}`, the very token `GET /api/v1/hub/device/entitlement/`
/// returns. It is verified with the same key and the same [`cloud_client::verify_entitlement`]
/// as the daily tick, then applied like a successful tick ([`RevalidationState::apply_pushed`]),
/// and the shell's 60 s cache of `GET /api/entitlement` is expired so the new plan shows now.
///
/// There is no session and no key: the signature IS the authentication, which is why the door
/// is open to the SaaS and to nobody else in practice. `200 {"ok": true}` is the only answer the
/// SaaS reads as "delivered"; anything else and it falls back to redeploying the hub. Nothing
/// here touches a session: a lower `max_devices` evicts the extra device at its next sign-in
/// (`mint_session`), never in the middle of a sale.
///
/// An RSA verification is not free and the door is open, so a caller that keeps sending tokens
/// that do not apply is locked out ([`crate::login_throttle`], keyed by the address the proxy
/// saw) BEFORE the hub verifies anything else it sends.
pub(crate) async fn push_refresh(
    axum::extract::State(st): axum::extract::State<crate::AppState>,
    headers: axum::http::HeaderMap,
    body: axum::body::Bytes,
) -> axum::response::Response {
    use axum::http::StatusCode;

    let key = push_throttle_key(&headers);
    if st.login_throttle.locked_for(&key).is_some() {
        return push_refused(StatusCode::TOO_MANY_REQUESTS, "entitlement_push_throttled");
    }
    let token = serde_json::from_slice::<Value>(&body)
        .ok()
        .and_then(|v| v.get("token").and_then(Value::as_str).map(str::to_owned))
        .filter(|t| !t.is_empty());
    let Some(token) = token else {
        return push_refused(StatusCode::BAD_REQUEST, "entitlement_token_missing");
    };
    // The key the boot resolved for user JWTs is the same pair the SaaS signs entitlements
    // with. A hub that could not fetch it at boot asks now; if the Cloud does not answer, the
    // push was not applied and the SaaS falls back to redeploying — never counted against it.
    let public_key = match &st.config.jwt_public_key {
        Some(pem) => pem.clone(),
        None => match crate::boot::fetch_jwt_public_key(&st.config.cloud_base_url).await {
            Some(pem) => pem,
            None => {
                tracing::warn!("entitlement push: no public key to verify it with");
                return push_refused(
                    StatusCode::SERVICE_UNAVAILABLE,
                    "entitlement_key_unavailable",
                );
            }
        },
    };
    let now = now_unix();
    let claims = match cloud_client::verify_entitlement(&token, &public_key, now) {
        Ok(claims) => claims,
        Err(error) => {
            // `?` over the text and never `%` (hub#2297): the door is open and `jsonwebtoken`
            // repeats an unknown `alg` verbatim, so a raw `\n` used to end this line and start
            // one that read as `event=auth_failed … client=<another shop>`. `Debug` of the
            // string quotes it and escapes every control character, so it stays one field.
            tracing::warn!(
                error = ?error.to_string(),
                "entitlement push refused: token does not verify"
            );
            st.login_throttle.record_failure(&key);
            return push_refused(StatusCode::UNAUTHORIZED, "entitlement_token_invalid");
        }
    };
    let applied = match st.entitlement.write() {
        Ok(mut guard) => guard.apply_pushed(claims, &st.hub_id(), now),
        Err(_) => {
            return push_refused(
                StatusCode::INTERNAL_SERVER_ERROR,
                "entitlement_state_unavailable",
            )
        }
    };
    match applied {
        Ok(()) => {
            st.login_throttle.record_success(&key);
            if let Ok(mut cache) = st.entitlement_proxy.write() {
                cache.invalidate();
            }
            tracing::info!("entitlement pushed by the Cloud applied");
            (
                StatusCode::OK,
                axum::Json(serde_json::json!({ "ok": true })),
            )
                .into_response()
        }
        Err(refusal) => {
            st.login_throttle.record_failure(&key);
            tracing::warn!(?refusal, "entitlement push refused");
            match refusal {
                PushRefusal::WrongHub => {
                    push_refused(StatusCode::FORBIDDEN, "entitlement_wrong_hub")
                }
                PushRefusal::Stale => push_refused(StatusCode::CONFLICT, "entitlement_stale"),
            }
        }
    }
}

/// What the push guard counts against: the LAST `X-Forwarded-For` hop — the one the proxy in
/// front of the hub appended, not one the caller wrote (same reasoning as the public door,
/// `public_door::throttle_key`). With no proxy header every caller shares one counter.
fn push_throttle_key(headers: &axum::http::HeaderMap) -> String {
    let client = headers
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok())
        .and_then(|v| v.rsplit(',').next())
        .map(str::trim)
        .filter(|v| !v.is_empty())
        .unwrap_or("direct");
    format!("entitlement-push:ip:{client}")
}

fn push_refused(status: axum::http::StatusCode, code: &str) -> axum::response::Response {
    (
        status,
        axum::Json(serde_json::json!({
            "ok": false,
            "error": { "code": code, "message": code },
        })),
    )
        .into_response()
}

/// Ejecuta un GET de una `PreparedRequest` del `CloudClient` y devuelve el body si es 2xx.
async fn exec_get(
    http: &reqwest::Client,
    req: cloud_client::PreparedRequest,
) -> Result<String, String> {
    let mut r = http.get(&req.url);
    for (k, v) in req.headers {
        r = r.header(k, v);
    }
    let resp = r.send().await.map_err(|e| e.to_string())?;
    let status = resp.status();
    if !status.is_success() {
        return Err(format!("{}: status {status}", req.url));
    }
    resp.text().await.map_err(|e| e.to_string())
}

/// Unix-ts actual (segundos). `0` si el reloj está antes de EPOCH (imposible en la práctica).
pub fn now_unix() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// Código estable con el que el hub cuenta que el Cloud le está limitando la tasa. La UI traduce
/// por CÓDIGO (ADR-0055): la frase de DRF (`"Request was throttled. Expected available in 2828
/// seconds."`) es inglesa, la escribe otro sistema y llegó a pintarse tal cual dentro de una
/// pantalla en español (hub#1167).
pub const CLOUD_RATE_LIMITED: &str = "cloud_rate_limited";

/// Ventana de frescura del proxy `GET /api/entitlement`.
///
/// El shell pregunta por el entitlement una vez por `focus` de ventana y otra por cada vista de
/// módulo que monta, así que un minuto de uso normal son muchas preguntas y **cero** cambios de
/// plan. La verdad de fondo se mueve en días —el job de revalidación firmado corre cada 24 h
/// ([`DEFAULT_REVALIDATE_SECS`])—, así que 60 s es holgadamente conservador y aun así convierte
/// una ráfaga entera en UNA llamada. No se sube más porque una compra hecha en otra pestaña tiene
/// que verse pronto; ese caso además tiene su propio botón, que consulta otra ruta.
pub const PROXY_TTL_SECS: i64 = 60;

/// Backoff que se aplica ante un 429 **sin** `Retry-After` utilizable. Con cabecera se respeta la
/// que mande el SaaS: es él quien sabe cuánto le queda a su ventana (en prod se han visto 2828 s).
pub const RATE_LIMIT_FALLBACK_BACKOFF_SECS: i64 = 300;

/// Tope del backoff que aceptamos de la cabecera. Un `Retry-After` disparatado (o corrupto) no
/// puede dejar al hub sin volver a preguntar por su entitlement durante horas: pasado este tope
/// se reintenta igual, y como mucho se come otro 429 —barato— en lugar de quedarse ciego.
pub const RATE_LIMIT_MAX_BACKOFF_SECS: i64 = 3_600;

/// Caché del proxy `GET /api/entitlement` (hub#1167).
///
/// Tiene DOS trabajos, y conviene no confundirlos:
///
///  - **No amplificar**: dentro de [`PROXY_TTL_SECS`] se contesta con el cuerpo guardado y no se
///    sale a la red. El 429 de fondo lo causa el SaaS (saas#1640: `AnonRateThrottle` 100/h keyed
///    por IP, compartido por toda la flota), pero el shell lo dispara pidiendo N veces lo mismo.
///  - **Amortiguar**: cuando el Cloud dice 429, se sirve el ÚLTIMO cuerpo bueno aunque esté
///    caducado y se abre una ventana de backoff. Degradar a «sin módulos» apagaría módulos ya
///    comprados por un problema de tasa, que es exactamente el fallo que no puede ocurrir.
#[derive(Debug, Default)]
pub struct ProxyCache {
    /// Último cuerpo BUENO del Cloud (objeto JSON tal cual, sin el bloque aditivo `revalidation`,
    /// que se recalcula en cada respuesta porque es estado local y siempre es fresco).
    body: Option<Value>,
    /// Unix-ts en que se guardó `body`.
    fetched_at: Option<i64>,
    /// Unix-ts hasta el que NO se vuelve a salir a la red (ventana pedida por el SaaS).
    backoff_until: Option<i64>,
}

/// Celda compartida de la caché (handlers concurrentes), como [`SharedRevalidation`].
pub type SharedProxyCache = Arc<RwLock<ProxyCache>>;

/// Crea la celda compartida vacía (sin nada cacheado, sin backoff).
pub fn new_shared_proxy_cache() -> SharedProxyCache {
    Arc::new(RwLock::new(ProxyCache::default()))
}

/// Qué hacer con una pregunta del shell, decidido sin red y sin reloj propio (el `now` lo pasa el
/// llamador, como el resto de este módulo, para que sea testeable).
#[derive(Debug, Clone, PartialEq)]
pub enum Decision {
    /// Contestar con este cuerpo guardado: o está fresco, o el SaaS nos pidió no llamar y esto es
    /// lo último bueno que sabemos.
    Serve(Value),
    /// El SaaS nos está limitando y NO hay nada bueno guardado que servir. Es el único caso en que
    /// el shell se entera del rate-limit, y se entera por un código, no por la prosa del SaaS.
    RateLimited,
    /// Toca salir a la red.
    Ask,
}

impl ProxyCache {
    /// Decide sin salir a la red. El orden importa: el backoff manda sobre la frescura, porque
    /// mientras el SaaS diga «no me llames» servir algo viejo es mejor que otra llamada que ya
    /// sabemos que va a volver en 429 — y esa llamada la paga toda la flota (saas#1640).
    pub fn decide(&self, now: i64) -> Decision {
        if self.backoff_until.is_some_and(|until| now < until) {
            return match &self.body {
                Some(body) => Decision::Serve(body.clone()),
                None => Decision::RateLimited,
            };
        }
        match &self.body {
            Some(body) if self.is_fresh(now) => Decision::Serve(body.clone()),
            _ => Decision::Ask,
        }
    }

    /// ¿El cuerpo guardado sigue dentro de la ventana de frescura?
    pub fn is_fresh(&self, now: i64) -> bool {
        match (&self.body, self.fetched_at) {
            (Some(_), Some(at)) => now.saturating_sub(at) < PROXY_TTL_SECS,
            _ => false,
        }
    }

    /// El último cuerpo bueno, **sin mirar la edad**: es lo que se sirve cuando el Cloud limita.
    /// Un entitlement de hace unos minutos es infinitamente mejor que un error, y el gate real
    /// vive en el servidor de todos modos (el proxy es UX + defensa en profundidad).
    pub fn last_good(&self) -> Option<&Value> {
        self.body.as_ref()
    }

    /// Guarda una respuesta buena del Cloud y cierra cualquier backoff abierto.
    pub fn store_success(&mut self, body: Value, now: i64) {
        self.body = Some(body);
        self.fetched_at = Some(now);
        self.backoff_until = None;
    }

    /// Abre la ventana de backoff tras un 429. `retry_after_secs` es lo que dijo la cabecera
    /// `Retry-After`; si no vino, no era un número o es disparatada, se aplica el default acotado.
    pub fn open_backoff(&mut self, retry_after_secs: Option<i64>, now: i64) {
        let window = retry_after_secs
            .filter(|s| *s > 0)
            .map(|s| s.min(RATE_LIMIT_MAX_BACKOFF_SECS))
            .unwrap_or(RATE_LIMIT_FALLBACK_BACKOFF_SECS);
        self.backoff_until = Some(now.saturating_add(window));
    }

    /// Marca lo guardado como caducado **sin tirarlo**: la siguiente pregunta vuelve a salir a la
    /// red, pero si el Cloud limita seguimos teniendo el último cuerpo bueno que servir. Es el
    /// gesto de «ha pasado algo que hace vieja la respuesta» (y el que usan los tests para
    /// simular el paso del tiempo sin un reloj falso).
    pub fn invalidate(&mut self) {
        self.fetched_at = None;
        self.backoff_until = None;
    }
}

#[cfg(test)]
mod proxy_cache_tests {
    use super::*;

    fn body() -> Value {
        serde_json::json!({ "modules": [] })
    }

    /// Dentro de la ventana de frescura no se sale a la red: es lo que convierte la ráfaga de
    /// `focus` del shell en UNA sola llamada al SaaS.
    #[test]
    fn un_cuerpo_fresco_se_sirve_sin_preguntar_al_cloud() {
        let mut cache = ProxyCache::default();
        cache.store_success(body(), 1_000);

        assert_eq!(cache.decide(1_000), Decision::Serve(body()));
        assert_eq!(
            cache.decide(1_000 + PROXY_TTL_SECS - 1),
            Decision::Serve(body())
        );
        assert_eq!(cache.decide(1_000 + PROXY_TTL_SECS), Decision::Ask);
    }

    /// El backoff manda sobre la frescura: con la ventana abierta se sirve lo último bueno aunque
    /// esté caducado, porque la alternativa es una llamada que ya sabemos que vuelve en 429.
    #[test]
    fn con_backoff_abierto_se_sirve_lo_ultimo_bueno_aunque_este_caducado() {
        let mut cache = ProxyCache::default();
        cache.store_success(body(), 0);
        cache.open_backoff(Some(600), 1_000);

        assert!(!cache.is_fresh(1_001), "el cuerpo ya está caducado");
        assert_eq!(cache.decide(1_001), Decision::Serve(body()));
        assert_eq!(
            cache.decide(1_600),
            Decision::Ask,
            "cerrada la ventana, se vuelve a preguntar"
        );
    }

    /// Sin nada bueno guardado, el rate-limit sí se le cuenta al shell — pero como decisión
    /// explícita, no como un error del Cloud reenviado tal cual.
    #[test]
    fn sin_cuerpo_guardado_el_backoff_responde_rate_limited() {
        let mut cache = ProxyCache::default();
        cache.open_backoff(Some(600), 1_000);

        assert_eq!(cache.decide(1_500), Decision::RateLimited);
    }

    /// Un `Retry-After` disparatado (o corrupto) no puede dejar al hub sin volver a preguntar
    /// durante horas: se acota. Y si no viene, se aplica el default — nunca cero, que sería seguir
    /// golpeando la puerta que acaba de decirnos que no.
    #[test]
    fn el_retry_after_se_acota_y_los_valores_invalidos_caen_al_default() {
        let cases = [
            (Some(600_i64), 600_i64),
            (Some(999_999), RATE_LIMIT_MAX_BACKOFF_SECS),
            (None, RATE_LIMIT_FALLBACK_BACKOFF_SECS),
            (Some(0), RATE_LIMIT_FALLBACK_BACKOFF_SECS),
            (Some(-5), RATE_LIMIT_FALLBACK_BACKOFF_SECS),
        ];
        for (header, expected_window) in cases {
            let mut cache = ProxyCache::default();
            cache.open_backoff(header, 1_000);
            // La ventana sigue cerrada un instante antes de expirar y abierta justo al expirar.
            assert_eq!(
                cache.decide(1_000 + expected_window - 1),
                Decision::RateLimited,
                "Retry-After {header:?} tenía que dar una ventana de {expected_window}s"
            );
            assert_eq!(
                cache.decide(1_000 + expected_window),
                Decision::Ask,
                "Retry-After {header:?}: pasada la ventana se vuelve a preguntar"
            );
        }
    }

    /// Un refresco bueno cierra el backoff: el SaaS ya nos habla otra vez.
    #[test]
    fn una_respuesta_buena_cierra_la_ventana_de_backoff() {
        let mut cache = ProxyCache::default();
        cache.open_backoff(Some(3_000), 1_000);
        assert_eq!(cache.decide(1_500), Decision::RateLimited);

        cache.store_success(body(), 1_500);
        assert_eq!(cache.decide(1_501), Decision::Serve(body()));
    }

    /// `invalidate()` fuerza el siguiente viaje a la red pero NO tira lo guardado: si ese viaje se
    /// come un 429, seguimos teniendo un entitlement bueno que servir en vez de apagar módulos.
    #[test]
    fn invalidate_caduca_pero_no_tira_el_ultimo_cuerpo_bueno() {
        let mut cache = ProxyCache::default();
        cache.store_success(body(), 1_000);

        cache.invalidate();

        assert_eq!(cache.decide(1_000), Decision::Ask);
        assert_eq!(cache.last_good(), Some(&body()));
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use cloud_client::EntitledModule;

    /// Claims de prueba: construidas a mano (los campos son `pub`), sin firmar — la regla de
    /// bloqueo opera sobre claims YA verificadas (la firma la cubre `verify_entitlement`).
    fn claims(modules: &[&str], grace_until: i64) -> EntitlementClaims {
        EntitlementClaims {
            hub_id: "h1".into(),
            modules: modules
                .iter()
                .map(|id| EntitledModule {
                    module_id: (*id).to_string(),
                    tier: "premium".into(),
                    version: "1.0.0".into(),
                })
                .collect(),
            iat: 1_000,
            exp: 2_000,
            grace_until,
            paid_grace_until: None,
            plan: None,
            max_devices: 0,
            max_database_size_gb: 0,
            max_users: 0,
        }
    }

    /// Como [`claims`] pero con `tier` explícito por módulo (regla (b): solo los DE PAGO).
    fn claims_tiered(modules: &[(&str, &str)], grace_until: i64) -> EntitlementClaims {
        EntitlementClaims {
            hub_id: "h1".into(),
            modules: modules
                .iter()
                .map(|(id, tier)| EntitledModule {
                    module_id: (*id).to_string(),
                    tier: (*tier).to_string(),
                    version: "1.0.0".into(),
                })
                .collect(),
            iat: 1_000,
            exp: 2_000,
            grace_until,
            paid_grace_until: None,
            plan: None,
            max_devices: 0,
            max_database_size_gb: 0,
            max_users: 0,
        }
    }

    #[test]
    fn tras_fallos_y_gracia_vencida_los_tiers_free_no_se_bloquean() {
        // Decisión del fundador: solo el módulo DE PAGO deja de funcionar. Los free son
        // locales por diseño (offline-first, ADR-0040) y siguen SIEMPRE, incluso con el
        // hub incomunicado más allá de la gracia.
        let mut st = RevalidationState::default();
        st.apply_success(
            claims_tiered(
                &[
                    ("pos", "premium"),
                    ("caja", "basic"),
                    ("agenda", "essential"),
                    ("notas", "free"),
                ],
                5_000,
            ),
            1_500,
        );
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        assert!(st.is_blocked("pos", 9_000)); // de pago → bloquea (fallos>=3 AND gracia vencida)
        assert!(!st.is_blocked("caja", 9_000)); // basic → gratis (ADR-0006), nunca por la rama (b)
        assert!(!st.is_blocked("agenda", 9_000)); // essential → gratis
        assert!(!st.is_blocked("notas", 9_000)); // free → gratis
    }

    #[test]
    fn tier_desconocido_o_vacio_cuenta_como_de_pago_en_la_rama_b() {
        // Fail-closed SOLO en la rama (b) (que ya exige 3 fallos + gracia vencida): un tier
        // que no sabemos que sea gratuito se trata como premium.
        let mut st = RevalidationState::default();
        st.apply_success(claims_tiered(&[("x", "pro"), ("y", "")], 5_000), 1_500);
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        assert!(st.is_blocked("x", 9_000)); // tier desconocido → como de pago
        assert!(st.is_blocked("y", 9_000)); // tier vacío → como de pago
    }

    #[test]
    fn fuera_de_claims_bloquea_inmediato_sea_cual_sea_el_tier() {
        // La regla (a) NO cambia: fuera del último refresh OK = verdad del servidor
        // (revocado/no comprado) → bloqueo inmediato; el tier ni se conoce.
        let mut st = RevalidationState::default();
        st.apply_success(claims_tiered(&[("caja", "basic")], 50_000), 1_500);
        assert!(st.is_blocked("pos", 1_600)); // sin fallos y con gracia vigente: da igual
        assert!(!st.is_blocked("caja", 1_600));
    }

    #[test]
    fn blocked_modules_tras_gracia_solo_contiene_de_pago_o_revocados() {
        // El bloque `revalidation` del proxy hereda la regla: tras fallos+gracia solo
        // aparecen los de pago (rama b) y los fuera de claims (rama a); los free nunca.
        let mut st = RevalidationState::default();
        st.apply_success(
            claims_tiered(&[("pos", "premium"), ("caja", "basic")], 5_000),
            1_500,
        );
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        let installed = vec![
            "pos".to_string(),
            "caja".to_string(),
            "revocado".to_string(),
        ];
        assert_eq!(
            st.blocked_modules(&installed, 9_000),
            vec!["pos".to_string(), "revocado".to_string()]
        );
    }

    #[test]
    fn sin_refresh_exitoso_nunca_bloquea() {
        // Fail-open: dev/local sin enrolar o hub recién arrancado — la autoridad es el SaaS.
        let st = RevalidationState::default();
        assert!(!st.is_blocked("pos", 999_999));
        assert_eq!(st.grace_until(), None);
    }

    #[test]
    fn modulo_fuera_del_ultimo_refresh_exitoso_bloquea_inmediato() {
        // Verdad del servidor: el último refresh OK no incluye `pos` → bloqueado YA (sin
        // esperar fallos ni gracia). `inventory` sí está → pasa.
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["inventory"], 9_000), 1_500);
        assert!(st.is_blocked("pos", 1_600));
        assert!(!st.is_blocked("inventory", 1_600));
    }

    #[test]
    fn dos_fallos_con_gracia_vencida_no_bloquea() {
        // Regla = fallos >= 3 AND now > grace: con solo 2 fallos NO bloquea aunque la gracia
        // haya vencido (el token sigue siendo la última verdad conocida).
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 5_000), 1_500);
        st.apply_failure(6_000);
        st.apply_failure(7_000);
        assert!(!st.is_blocked("pos", 8_000)); // now > grace_until (5_000), pero fallos < 3
    }

    #[test]
    fn cinco_fallos_con_gracia_vigente_no_bloquea() {
        // Muchos fallos pero la gracia del último token válido sigue vigente → no bloquea.
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 50_000), 1_500);
        for i in 0..5 {
            st.apply_failure(2_000 + i);
        }
        assert!(!st.is_blocked("pos", 10_000)); // fallos >= 3, pero now < grace_until (50_000)
    }

    #[test]
    fn tres_fallos_y_gracia_vencida_bloquea() {
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 5_000), 1_500);
        st.apply_failure(6_000);
        st.apply_failure(7_000);
        st.apply_failure(8_000);
        assert!(st.is_blocked("pos", 9_000)); // fallos == 3 AND now > grace_until
    }

    #[test]
    fn paid_grace_until_menor_bloquea_al_de_pago_aunque_grace_until_siga_vigente() {
        // Claim ADITIVO del SaaS (2026-07-12): gracia de pago de 5 días, SEPARADA de la global
        // de 7 (`grace_until`, gate de la app). Con paid_grace_until (5_000) < grace_until
        // (50_000), el módulo DE PAGO se bloquea en cuanto fallos >= 3 AND now > paid_grace_until,
        // aunque la gracia global siga vigente. Los tiers gratuitos siguen exentos de la rama (b).
        let mut st = RevalidationState::default();
        let mut c = claims_tiered(
            &[
                ("pos", "premium"),
                ("caja", "basic"),
                ("agenda", "essential"),
                ("notas", "free"),
            ],
            50_000,
        );
        c.paid_grace_until = Some(5_000);
        st.apply_success(c, 1_500);
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        assert!(st.is_blocked("pos", 9_000)); // de pago: now > paid_grace (5_000), now < grace (50_000)
        assert!(!st.is_blocked("pos", 4_000)); // antes de la gracia de pago aún no bloquea
        assert!(!st.is_blocked("caja", 9_000)); // basic → gratis, nunca por la rama (b)
        assert!(!st.is_blocked("agenda", 9_000)); // essential → gratis
        assert!(!st.is_blocked("notas", 9_000)); // free → gratis
    }

    #[test]
    fn sin_paid_grace_until_el_de_pago_cae_a_grace_until_como_hoy() {
        // Retrocompat: tokens antiguos sin el claim (paid_grace_until = None, ver helpers) →
        // la rama (b) usa `grace_until` exactamente igual que antes.
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 5_000), 1_500);
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        assert!(st.is_blocked("pos", 9_000)); // fallos >= 3 AND now > grace_until
        assert!(!st.is_blocked("pos", 4_000)); // con la gracia global vigente no bloquea
    }

    #[test]
    fn revalidation_json_expone_paid_grace_until_ademas_de_grace_until() {
        // El bloque aditivo del proxy expone AMBAS gracias: la UI pinta «funcionará hasta
        // {fecha}» con la de pago si viene, sin perder la global existente.
        let mut st = RevalidationState::default();
        let mut c = claims(&["inventory"], 9_000);
        c.paid_grace_until = Some(4_000);
        st.apply_success(c, 1_500);
        let v = st.revalidation_json(&["inventory".to_string()], 2_500);
        assert_eq!(v["grace_until"], serde_json::json!(9_000)); // el existente no se sustituye
        assert_eq!(v["paid_grace_until"], serde_json::json!(4_000));
        assert_eq!(st.paid_grace_until(), Some(4_000));

        // Sin el claim (tokens antiguos) el campo va a null y el helper a None.
        let mut st2 = RevalidationState::default();
        st2.apply_success(claims(&["inventory"], 9_000), 1_500);
        let v2 = st2.revalidation_json(&["inventory".to_string()], 2_500);
        assert_eq!(v2["paid_grace_until"], Value::Null);
        assert_eq!(st2.paid_grace_until(), None);
    }

    #[test]
    fn exito_resetea_contador_y_desbloquea() {
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 5_000), 1_500);
        for i in 0..3 {
            st.apply_failure(6_000 + i);
        }
        assert!(st.is_blocked("pos", 9_000));

        // Un refresh exitoso posterior resetea el contador y renueva la gracia.
        st.apply_success(claims(&["pos"], 99_000), 9_500);
        assert_eq!(st.consecutive_failures, 0);
        assert_eq!(st.last_refresh_ok_at, Some(9_500));
        assert_eq!(st.grace_until(), Some(99_000));
        assert!(!st.is_blocked("pos", 10_000));
    }

    #[test]
    fn apply_failure_actualiza_last_check() {
        let mut st = RevalidationState::default();
        st.apply_failure(4_000);
        assert_eq!(st.last_check_at, Some(4_000));
        assert_eq!(st.consecutive_failures, 1);
        assert_eq!(st.last_refresh_ok_at, None); // un fallo no toca el último OK
    }

    #[test]
    fn blocked_modules_filtra_instalados() {
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["inventory"], 9_000), 1_500);
        let installed = vec!["inventory".to_string(), "pos".to_string()];
        assert_eq!(
            st.blocked_modules(&installed, 2_000),
            vec!["pos".to_string()]
        );
    }

    #[test]
    fn revalidation_json_expone_estado_para_la_ui() {
        // El bloque aditivo del proxy: blocked_modules + grace_until + last_check (+ extras).
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["inventory"], 9_000), 1_500);
        st.apply_failure(2_000);
        let installed = vec!["inventory".to_string(), "pos".to_string()];
        let v = st.revalidation_json(&installed, 2_500);
        assert_eq!(v["blocked_modules"], serde_json::json!(["pos"]));
        assert_eq!(v["grace_until"], serde_json::json!(9_000));
        assert_eq!(v["last_check"], serde_json::json!(2_000));
        assert_eq!(v["last_refresh_ok_at"], serde_json::json!(1_500));
        assert_eq!(v["consecutive_failures"], serde_json::json!(1));
    }

    #[test]
    fn record_outcome_aplica_exito_y_fallo_sobre_la_celda() {
        // El tick del job separa red (fetch) de estado: aquí se testea el estado inyectado.
        let cell = new_shared();
        record_outcome(&cell, Ok(claims(&["pos"], 9_000)), 1_000);
        {
            let g = cell.read().unwrap();
            assert_eq!(g.consecutive_failures, 0);
            assert_eq!(g.last_refresh_ok_at, Some(1_000));
        }
        record_outcome(&cell, Err("red caída".into()), 2_000);
        let g = cell.read().unwrap();
        assert_eq!(g.consecutive_failures, 1);
        assert_eq!(g.last_check_at, Some(2_000));
        assert!(g.last_claims.is_some()); // el fallo NO borra la última verdad conocida
    }

    #[test]
    fn max_devices_viene_del_ultimo_token_o_cero_sin_estado() {
        // ADR-0154: el límite de dispositivos lo aporta el claim `max_devices` del último token
        // válido. Sin refresh exitoso previo → 0 (ilimitado, fail-open: sin takeover local, la
        // autoridad es el SaaS).
        let st = RevalidationState::default();
        assert_eq!(st.max_devices(), 0);

        let mut st2 = RevalidationState::default();
        let mut c = claims(&["pos"], 9_000);
        c.max_devices = 1;
        st2.apply_success(c, 1_500);
        assert_eq!(st2.max_devices(), 1);
    }

    #[test]
    fn max_users_viene_del_ultimo_token_o_cero_sin_estado() {
        // saas#1953/ADR-0474: el tope de usuarios lo aporta el claim `max_users`. Sin refresh
        // exitoso previo → 0 (ilimitado, fail-open), igual que el de dispositivos.
        let st = RevalidationState::default();
        assert_eq!(st.max_users(), 0);

        let mut st2 = RevalidationState::default();
        let mut c = claims(&["pos"], 9_000);
        c.max_users = 3;
        st2.apply_success(c, 1_500);
        assert_eq!(st2.max_users(), 3);
    }

    #[test]
    fn cuota_bd_viene_del_ultimo_token_o_cero_sin_estado() {
        let st = RevalidationState::default();
        assert_eq!(st.max_database_size_gb(), 0);

        let mut st2 = RevalidationState::default();
        let mut c = claims(&["pos"], 9_000);
        c.max_database_size_gb = 5;
        st2.apply_success(c, 1_500);
        assert_eq!(st2.max_database_size_gb(), 5);
    }

    /// hub#2105: a token the SaaS pushes lands exactly like a successful tick — new claims,
    /// counter back to zero — so a plan upgrade applies without waiting a day or a restart.
    #[test]
    fn a_pushed_token_applies_like_a_successful_refresh() {
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 5_000), 1_500);
        st.apply_failure(1_600);

        let mut upgraded = claims(&["pos", "inventory"], 9_000);
        upgraded.iat = 2_000;
        upgraded.max_devices = 3;
        assert_eq!(st.apply_pushed(upgraded.clone(), "h1", 2_100), Ok(()));

        assert_eq!(st.last_claims, Some(upgraded));
        assert_eq!(st.last_refresh_ok_at, Some(2_100));
        assert_eq!(st.consecutive_failures, 0);
        assert_eq!(st.max_devices(), 3);
    }

    /// The first token a freshly booted hub hears about may be the pushed one.
    #[test]
    fn a_pushed_token_applies_on_a_hub_with_no_previous_refresh() {
        let mut st = RevalidationState::default();
        assert_eq!(
            st.apply_pushed(claims(&["pos"], 9_000), "h1", 1_100),
            Ok(())
        );
        assert_eq!(st.last_refresh_ok_at, Some(1_100));
    }

    /// A token signed for ANOTHER hub is a valid signature on the wrong door: never applied.
    #[test]
    fn a_pushed_token_for_another_hub_is_refused_and_changes_nothing() {
        let mut st = RevalidationState::default();
        st.apply_success(claims(&["pos"], 5_000), 1_500);

        let mut foreign = claims(&["pos", "inventory"], 9_000);
        foreign.hub_id = "h2".into();
        foreign.iat = 2_000;
        assert_eq!(
            st.apply_pushed(foreign, "h1", 2_100),
            Err(PushRefusal::WrongHub)
        );
        assert_eq!(st.last_claims, Some(claims(&["pos"], 5_000)));
        assert_eq!(st.last_refresh_ok_at, Some(1_500));
    }

    /// Anti-replay: an older token (say, the free plan captured before the upgrade) cannot roll
    /// the hub back. The same token again is harmless and idempotent.
    #[test]
    fn a_pushed_token_older_than_the_current_one_is_refused() {
        let mut st = RevalidationState::default();
        let mut current = claims(&["pos", "inventory"], 9_000);
        current.iat = 5_000;
        st.apply_success(current.clone(), 5_100);

        let mut older = claims(&["pos"], 9_000);
        older.iat = 4_999;
        assert_eq!(st.apply_pushed(older, "h1", 5_200), Err(PushRefusal::Stale));
        assert_eq!(st.last_claims, Some(current.clone()));
        assert_eq!(st.last_refresh_ok_at, Some(5_100));

        assert_eq!(st.apply_pushed(current, "h1", 5_300), Ok(()));
    }

    /// The push guard counts the hop the proxy appended, never one the caller wrote: reading the
    /// first entry would hand an attacker a fresh counter on every request.
    #[test]
    fn the_push_guard_counts_the_hop_the_caller_could_not_forge() {
        let mut headers = axum::http::HeaderMap::new();
        headers.insert("x-forwarded-for", "1.2.3.4, 198.51.100.7".parse().unwrap());
        assert_eq!(
            push_throttle_key(&headers),
            "entitlement-push:ip:198.51.100.7"
        );
        assert_eq!(
            push_throttle_key(&axum::http::HeaderMap::new()),
            "entitlement-push:ip:direct"
        );
    }

    #[test]
    fn intervalo_del_job_default_y_override() {
        assert_eq!(interval_secs(None), DEFAULT_REVALIDATE_SECS);
        assert_eq!(interval_secs(Some("3600")), 3_600);
        assert_eq!(interval_secs(Some("no-numero")), DEFAULT_REVALIDATE_SECS);
        assert_eq!(interval_secs(Some("0")), DEFAULT_REVALIDATE_SECS);
        assert_eq!(interval_secs(Some("")), DEFAULT_REVALIDATE_SECS);
    }

    /// Public half of the throwaway pair the push tests sign with: the forged token is refused
    /// while its header is parsed, so the key only has to be a valid RSA PEM.
    const PUSH_PUB: &str = "-----BEGIN PUBLIC KEY-----
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

    async fn push_state() -> crate::AppState {
        let db = erplora_db::testutil::fresh_db().await;
        let rt = erplora_runtime::Runtime::with_hub_id(Box::new(db), "hub-push-log");
        rt.ensure_system_tables().await.unwrap();
        let temp = std::env::temp_dir().join(format!("erplora-ent-log-{}", std::process::id()));
        let cfg = crate::HubConfig {
            demo: false,
            hub_id: "hub-push-log".into(),
            cloud_base_url: "https://example.invalid".into(),
            module_cache: temp.join("modules-cache"),
            auth_mode: crate::state::AuthMode::Session,
            jwt_public_key: Some(PUSH_PUB.into()),
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

    /// POSTs a token whose JWT header names the algorithm `alg` through the real door and
    /// returns the status plus what reached the log. `jsonwebtoken` refuses an unknown `alg`
    /// with a serde error that repeats the value verbatim — the text a stranger controls.
    async fn logged_push(alg: &str) -> (axum::http::StatusCode, String) {
        use base64::Engine as _;
        let b64 = base64::engine::general_purpose::URL_SAFE_NO_PAD;
        let header = b64.encode(serde_json::json!({ "alg": alg, "typ": "JWT" }).to_string());
        let token = format!("{header}.{}.{}", b64.encode("{}"), b64.encode("sig"));
        let body = serde_json::json!({ "token": token }).to_string();
        let st = push_state().await;
        let (sink, guard) = crate::log_capture::capture_scope();
        let response = push_refresh(
            axum::extract::State(st),
            axum::http::HeaderMap::new(),
            axum::body::Bytes::from(body),
        )
        .await;
        drop(guard);
        (response.status(), sink.text())
    }

    #[tokio::test]
    async fn hub2297_a_newline_in_a_pushed_token_cannot_forge_a_log_line() {
        // The door has no session and no key, and tracing escapes ESC but not `\n`: the refusal
        // used to end its line and start a second one that read exactly like a failed PIN.
        let (status, log) = logged_push(&format!("x\n{FORGED}")).await;
        assert_eq!(status, axum::http::StatusCode::UNAUTHORIZED);
        let lines: Vec<&str> = log.lines().collect();
        assert_eq!(
            lines.len(),
            1,
            "one refused push must be one line, got {log:?}"
        );
        assert!(
            lines[0].contains("entitlement push refused: token does not verify"),
            "the only line is not the refusal's: {log:?}"
        );
    }

    #[tokio::test]
    async fn hub2297_a_forged_event_stays_quoted_inside_the_error_field() {
        // Without a newline the fake text rode inside the refusal as bare `event=… client=…`
        // pairs, which a key=value reader cannot tell from the hub's own. Quoted, it is one value.
        let (_, log) = logged_push(&format!("x {FORGED}")).await;
        let line = log.lines().next().unwrap_or_default();
        let (_, error) = line
            .split_once(" error=\"")
            .unwrap_or_else(|| panic!("the error is not a quoted field: {log:?}"));
        assert!(
            error.ends_with('"') && error.contains(FORGED),
            "the forged text is not enclosed in the error field: {log:?}"
        );
    }

    #[test]
    fn revalidation_json_sin_estado_es_nulo_y_vacio() {
        // Estado inicial (fail-open): sin bloqueos y campos a null — la UI no pinta aviso.
        let st = RevalidationState::default();
        let v = st.revalidation_json(&["pos".to_string()], 1_000);
        assert_eq!(v["blocked_modules"], serde_json::json!([]));
        assert_eq!(v["grace_until"], Value::Null);
        assert_eq!(v["last_check"], Value::Null);
    }
}
