//! Autenticación del handshake WebSocket del Bridge (ADR-0050 §seguridad).
//!
//! **Por qué existe (agujero que cierra):** antes `ws_upgrade` aceptaba *cualquier* conexión a
//! `localhost:12321`. Como el Bridge habla con hardware físico (imprime, abre el cajón), cualquier
//! página web abierta en el mismo equipo podía conectarse al WS y disparar comandos. Este módulo
//! añade dos barreras en el handshake, ambas best-practice para servidores locales:
//!
//!   1. **Allowlist de `Origin`** — solo orígenes de confianza (loopback, `tauri://`,
//!      `https://localhost`, y los configurados por env) pueden hacer el upgrade. Frena el
//!      *cross-site WebSocket hijacking* desde una web de terceros.
//!   2. **Token de sesión compartido** — un secreto que el Hub conoce (env `BRIDGE_TOKEN`,
//!      entregado igual que `HUB_CLOUD_API_TOKEN`: inyectado por el shell/empaquetado). Se valida
//!      con comparación en tiempo constante. El navegador no puede fijar cabeceras en un
//!      `WebSocket`, así que el token se acepta por **cabecera** (`Authorization: Bearer` o
//!      `X-Hub-Session`) **o por query param** (`?token=…`).
//!
//! **Modelo (aprobado 2026-06-22, ADR-0050 §seguridad — fail-closed + emparejamiento):**
//!   - **El token es la frontera real, fail-CLOSED por defecto.** El token es *infalsificable* por un
//!     tercero (no conoce el secreto) **y agnóstico al dominio**, así que es lo único que aguanta que
//!     el tenant sirva la PWA desde su **propio dominio** (`pos.surestaurante.com`): el `Origin` no se
//!     puede enumerar de antemano, el token sí viaja igual. Por eso el token **siempre** se exige,
//!     salvo en modo dev explícito (`BRIDGE_DEV`).
//!   - **Origen del token** (en este orden): (1) `BRIDGE_TOKEN` inyectado (ECS/empaquetado, igual que
//!     `HUB_CLOUD_API_TOKEN`); (2) **emparejamiento**: si no se inyecta, el Bridge **genera** un token
//!     aleatorio en el primer arranque, lo **persiste** (`BRIDGE_TOKEN_FILE`, por defecto
//!     `bridge-token` junto al cwd, como `devices.json`) y muestra **una vez** el código para que el
//!     usuario lo empareje en la app. En arranques siguientes lo lee del fichero.
//!   - **`BRIDGE_DEV` (solo desarrollo)** desactiva la barrera de token (queda solo la allowlist de
//!     `Origin`), con un `warn` ruidoso. NUNCA en producción. Reemplaza al viejo "fail-open si falta
//!     el token", que era demasiado fácil de shippear sin querer.
//!   - **El `Origin` es defensa en profundidad**, no la puerta: rechaza `null`/orígenes foráneos, pero
//!     el dominio del tenant se inyecta vía `BRIDGE_ALLOWED_ORIGINS` al provisionar. El `Origin`
//!     ausente se permite (clientes nativos sin navegador no lo envían); el token sigue mandando.
//!   - El secreto **no se loggea nunca en validación**; solo se muestra **una vez** como código de
//!     emparejamiento al generarlo (canal local: la consola del operador en su propia máquina).

use std::path::{Path, PathBuf};

use axum::http::{HeaderMap, Uri};
use jsonwebtoken::{decode, Algorithm, DecodingKey, Validation};

/// Nombre de la cabecera propia de sesión del Hub (alternativa a `Authorization: Bearer`).
pub const SESSION_HEADER: &str = "x-hub-session";

/// Env var del secreto compartido del Bridge (inyectado: ECS/empaquetado).
pub const ENV_TOKEN: &str = "BRIDGE_TOKEN";
/// Env var de la ruta del fichero donde se persiste el token de emparejamiento.
pub const ENV_TOKEN_FILE: &str = "BRIDGE_TOKEN_FILE";
/// Env var que activa el **modo desarrollo** (desactiva la barrera de token). Cualquier valor
/// "truthy" (`1`/`true`/`yes`/`on`) la activa. NUNCA en producción.
pub const ENV_DEV: &str = "BRIDGE_DEV";
/// Env var de orígenes extra permitidos (CSV). P.ej. `https://app.erplora.com,https://hub.local`.
pub const ENV_ALLOWED_ORIGINS: &str = "BRIDGE_ALLOWED_ORIGINS";
/// Env var con la **clave pública RSA (PEM, SPKI)** para verificar la credencial JWT firmada. NO es
/// secreta: solo quien tiene la privada (SaaS/Hub) puede emitir tokens válidos.
pub const ENV_JWT_PUBLIC_KEY: &str = "BRIDGE_JWT_PUBLIC_KEY";
/// Env var con la **ruta** a un fichero con la clave pública PEM (alternativa a inyectarla inline).
pub const ENV_JWT_PUBLIC_KEY_FILE: &str = "BRIDGE_JWT_PUBLIC_KEY_FILE";
/// `aud` (audience) que DEBE llevar todo bridge-token, emitido por el SaaS. Es una **constante del
/// protocolo, NO configurable**: el Bridge es genérico e idéntico en toda máquina. Distingue un token
/// emitido PARA el Bridge de un token de login de usuario o de máquina → un token robado de otro
/// plano no mueve el hardware. Siempre se exige cuando hay verificación JWT.
pub const BRIDGE_AUDIENCE: &str = "erplora-bridge";
/// Env var de la base URL del SaaS del que el Bridge pide la clave pública
/// (`GET {saas}/api/v1/auth/public-key/`, mismo endpoint que el runtime del Hub). Tiene **default
/// horneado** ([`DEFAULT_SAAS_URL`]): el Bridge se autoconfigura con cero ajustes; solo un fork la toca.
pub const ENV_SAAS_URL: &str = "BRIDGE_SAAS_URL";
/// SaaS por defecto (producto de referencia). **El Bridge NO se vincula a ningún hub:** es el mismo
/// binario en toda máquina y sirve al hub cuya PWA esté abierta ahí. El `hub_id` del token es
/// informativo (lo emite el SaaS), no un pin de instalación.
pub const DEFAULT_SAAS_URL: &str = "https://erplora.com";

/// Nombre por defecto del fichero del token (junto al cwd, igual que `devices.json`).
const DEFAULT_TOKEN_FILE: &str = "bridge-token";

/// Resultado de evaluar el handshake. Mapea a un status HTTP cuando se rechaza.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AuthOutcome {
    /// Handshake permitido.
    Allowed,
    /// `Origin` no está en la allowlist → 403.
    ForbiddenOrigin,
    /// Token ausente o inválido → 401.
    Unauthorized,
}

impl AuthOutcome {
    /// Status HTTP del rechazo (`Allowed` no tiene status de error).
    pub fn status_code(self) -> axum::http::StatusCode {
        match self {
            AuthOutcome::Allowed => axum::http::StatusCode::OK,
            AuthOutcome::ForbiddenOrigin => axum::http::StatusCode::FORBIDDEN,
            AuthOutcome::Unauthorized => axum::http::StatusCode::UNAUTHORIZED,
        }
    }
}

/// Claims que nos interesan del JWT del Bridge. `exp`/`aud` los valida `jsonwebtoken` leyéndolos del
/// token (no hacen falta aquí); `hub_id` lo comprobamos nosotros contra el esperado si se configuró.
#[derive(serde::Deserialize)]
struct BridgeClaims {
    #[serde(default)]
    hub_id: Option<String>,
}

/// Verificador de la credencial **JWT firmada (RS256)** contra una clave **pública** configurada.
///
/// La clave pública NO es secreta: se puede shippear/leer sin riesgo — solo quien tiene la privada
/// (el SaaS/Hub, mismo par que firma los JWT de usuario, `crates/cloud-client`) puede emitir tokens
/// válidos. Por eso esta vía es **agnóstica al dominio**: un token válido prueba la autorización sin
/// depender del `Origin`, así el tenant sirve la PWA desde su propio dominio (`erp.midominio.com`)
/// sin allowlist por-dominio. `exp` obligatorio → tokens efímeros, resistentes a fugas.
#[derive(Clone)]
pub struct JwtVerifier {
    key: DecodingKey,
    expected_aud: Option<String>,
    expected_hub_id: Option<String>,
}

impl std::fmt::Debug for JwtVerifier {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Nunca volcamos la clave; solo los criterios de validación.
        f.debug_struct("JwtVerifier")
            .field("expected_aud", &self.expected_aud)
            .field("expected_hub_id", &self.expected_hub_id)
            .finish_non_exhaustive()
    }
}

impl JwtVerifier {
    /// Construye desde una clave pública RSA en PEM (SPKI). `aud`/`hub_id` esperados opcionales.
    pub fn from_rsa_pem(
        pem: &str,
        expected_aud: Option<String>,
        expected_hub_id: Option<String>,
    ) -> Result<Self, String> {
        let key = DecodingKey::from_rsa_pem(pem.as_bytes()).map_err(|e| e.to_string())?;
        Ok(Self { key, expected_aud, expected_hub_id })
    }

    /// `true` si `token` es un JWT RS256 válido: firma correcta contra la clave pública, **no
    /// expirado** (`exp` obligatorio), y `aud`/`hub_id` casan si se configuraron. Cualquier fallo
    /// (parse, firma, expiración, claim) → `false`. No hace I/O ni loggea el token.
    pub fn verify(&self, token: &str) -> bool {
        let mut validation = Validation::new(Algorithm::RS256);
        match self.expected_aud.as_deref() {
            Some(aud) => {
                validation.set_audience(&[aud]);
                // `jsonwebtoken` solo valida `aud` SI está presente (no lo exige por defecto). Sin
                // esto, un token de máquina/usuario sin `aud` pero con el `hub_id` correcto colaría
                // — anulando el propósito del audience dedicado. Lo hacemos claim REQUERIDO.
                validation.set_required_spec_claims(&["exp", "aud"]);
            }
            // Sin `aud` esperado, desactivamos esa comprobación.
            None => validation.validate_aud = false,
        }
        match decode::<BridgeClaims>(token, &self.key, &validation) {
            Ok(data) => match self.expected_hub_id.as_deref() {
                Some(expected) => data.claims.hub_id.as_deref() == Some(expected),
                None => true,
            },
            Err(_) => false,
        }
    }
}

/// Política de autenticación del Bridge. Inmutable tras construirse desde el entorno.
#[derive(Debug, Clone)]
pub struct BridgeAuth {
    /// Secreto compartido (token de emparejamiento simétrico); `None` si no hay vía simétrica.
    token: Option<String>,
    /// Verificador de la credencial JWT firmada (clave pública). `None` si no se configuró.
    jwt: Option<JwtVerifier>,
    /// `true` solo en modo dev (`BRIDGE_DEV`): sin barrera de credencial (queda solo `Origin`).
    dev_open: bool,
    /// Orígenes exactos extra permitidos además de los implícitos (loopback/tauri/localhost).
    extra_origins: Vec<String>,
}

impl BridgeAuth {
    /// Construye la política desde el entorno (fail-closed salvo `BRIDGE_DEV`).
    ///
    /// - `BRIDGE_DEV` truthy → barrera de token **desactivada** (solo `Origin`), con `warn`.
    /// - en cualquier otro caso → token **obligatorio**, resuelto por `resolve_token`
    ///   (`BRIDGE_TOKEN` inyectado → fichero persistido → genera+persiste+muestra el emparejamiento).
    pub fn from_env() -> Self {
        let extra_origins = std::env::var(ENV_ALLOWED_ORIGINS)
            .ok()
            .map(|csv| {
                csv.split(',')
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty())
                    .collect()
            })
            .unwrap_or_default();

        if dev_mode() {
            tracing::warn!(
                "{ENV_DEV} activo: el WS del Bridge NO exige token (solo allowlist de Origin). \
                 Es SOLO para desarrollo — nunca en producción."
            );
            return Self { token: None, jwt: None, dev_open: true, extra_origins };
        }

        let env_token = std::env::var(ENV_TOKEN).ok();
        let token = resolve_token(env_token, &token_file_path());
        let jwt = jwt_from_env();
        Self { token: Some(token), jwt, dev_open: false, extra_origins }
    }

    /// Constructor explícito (tests / arranque programático del sidecar Tauri, que construirá la
    /// política sin pasar por el entorno). El binario standalone usa `from_env`.
    ///
    /// `token: None` ⇒ barrera de credencial desactivada (semántica dev/local histórica), salvo que
    /// luego se añada un verificador con [`with_jwt`](Self::with_jwt).
    #[allow(dead_code)] // API pública: la consume el sidecar Tauri (futuro) y los tests.
    pub fn new(token: Option<String>, extra_origins: Vec<String>) -> Self {
        let dev_open = token.is_none();
        Self { token, jwt: None, dev_open, extra_origins }
    }

    /// Añade el verificador de JWT (clave pública) y activa la barrera de credencial (`dev_open=false`).
    /// Builder para tests / arranque programático; `from_env` lo cablea vía `BRIDGE_JWT_PUBLIC_KEY`.
    #[allow(dead_code)]
    pub fn with_jwt(mut self, jwt: JwtVerifier) -> Self {
        self.jwt = Some(jwt);
        self.dev_open = false;
        self
    }

    /// `true` si la barrera de token está activa (hay secreto configurado). Útil para que el
    /// consumidor decida si advertir/abortar en arranque fail-closed.
    #[allow(dead_code)] // API pública consumida por tests / arranque programático.
    pub fn token_required(&self) -> bool {
        self.token.is_some()
    }

    /// `true` si ya hay un verificador JWT (clave pública) configurado. `main` lo usa para decidir
    /// si pedir la clave al SaaS (solo si no llegó ya por el override de env).
    pub fn has_jwt(&self) -> bool {
        self.jwt.is_some()
    }

    /// Evalúa un handshake completo. Dos vías de credencial, en este orden:
    ///
    ///   1. **JWT firmado** (si hay verificador): un token válido autoriza desde **cualquier**
    ///      `Origin` — la firma ES la prueba, agnóstica al dominio (soporta el dominio propio del
    ///      tenant sin allowlist).
    ///   2. **Token simétrico** (emparejamiento): exige además que el `Origin` sea de confianza
    ///      (loopback/allowlist), porque el secreto es más filtrable (viaja en `?token=`).
    ///
    /// En modo dev (`dev_open`) no hay barrera de credencial: solo se comprueba el `Origin`.
    pub fn evaluate(&self, headers: &HeaderMap, uri: &Uri) -> AuthOutcome {
        // `Host` loopback (anti DNS-rebinding) — antes que nada, en cualquier modo.
        if !self.host_allowed(headers) {
            return AuthOutcome::ForbiddenOrigin;
        }

        let origin = headers
            .get(axum::http::header::ORIGIN)
            .and_then(|v| v.to_str().ok());

        // Modo dev: solo la barrera de `Origin`.
        if self.dev_open {
            return if self.origin_allowed(origin) {
                AuthOutcome::Allowed
            } else {
                AuthOutcome::ForbiddenOrigin
            };
        }

        let presented = presented_token(headers, uri);

        // (1) Vía JWT firmado — agnóstica al dominio.
        if let (Some(jwt), Some(tok)) = (&self.jwt, presented.as_deref()) {
            if jwt.verify(tok) {
                return AuthOutcome::Allowed;
            }
        }

        // (2) Vía token simétrico — el `Origin` es defensa en profundidad.
        if let Some(secret) = self.token.as_deref() {
            if !self.origin_allowed(origin) {
                return AuthOutcome::ForbiddenOrigin;
            }
            return match presented.as_deref() {
                Some(tok) if constant_time_eq(tok.as_bytes(), secret.as_bytes()) => {
                    AuthOutcome::Allowed
                }
                _ => AuthOutcome::Unauthorized,
            };
        }

        // (3) Solo-JWT configurado y el JWT no verificó → no autorizado.
        AuthOutcome::Unauthorized
    }

    /// `true` si la cabecera `Host` apunta a loopback (`localhost`/`127.0.0.1`/`[::1]`), con o sin
    /// puerto. **Cierra DNS rebinding**: un atacante que resuelva su dominio a 127.0.0.1 llega con
    /// `Host: attacker.com` (no loopback) → rechazado, en TODAS las rutas (incluida `/status`). Un
    /// `Host` ausente se permite (clientes nativos); el navegador SIEMPRE lo envía, así que no
    /// habilita el ataque. Aplica en `/status` y en el handshake de `/ws`.
    pub fn host_allowed(&self, headers: &HeaderMap) -> bool {
        let Some(host) = headers.get(axum::http::header::HOST).and_then(|v| v.to_str().ok()) else {
            return true; // clientes nativos sin `Host`; el navegador siempre lo envía.
        };
        is_loopback_host(host)
    }

    /// `true` si el `Origin` es de confianza. `None` (cliente no-navegador) se permite.
    pub fn origin_allowed(&self, origin: Option<&str>) -> bool {
        let Some(origin) = origin else {
            // Clientes nativos (sidecar Tauri local, pruebas, curl) no envían `Origin`.
            return true;
        };
        // Algunos navegadores mandan `Origin: null` (sandbox / file://). Nunca de confianza.
        if origin.eq_ignore_ascii_case("null") {
            return false;
        }
        if is_builtin_trusted_origin(origin) {
            return true;
        }
        self.extra_origins.iter().any(|o| o.eq_ignore_ascii_case(origin))
    }

    /// `true` si el token presentado (cabecera o query) casa con el secreto. Sin secreto
    /// configurado, siempre `true` (barrera desactivada). `evaluate` inlinea esta comprobación en su
    /// vía simétrica; se conserva como API pública (tests / arranque programático del sidecar).
    #[allow(dead_code)]
    pub fn token_valid(&self, headers: &HeaderMap, uri: &Uri) -> bool {
        let Some(secret) = self.token.as_deref() else {
            return true; // barrera desactivada
        };
        match presented_token(headers, uri) {
            Some(presented) => constant_time_eq(presented.as_bytes(), secret.as_bytes()),
            None => false,
        }
    }
}

/// `true` si `BRIDGE_DEV` tiene un valor truthy (desactiva la barrera de token — solo dev).
fn dev_mode() -> bool {
    std::env::var(ENV_DEV).ok().as_deref().map(is_truthy).unwrap_or(false)
}

/// Interpreta un valor de env como booleano: `1`/`true`/`yes`/`on` (case-insensitive) ⇒ `true`.
fn is_truthy(v: &str) -> bool {
    matches!(v.trim().to_ascii_lowercase().as_str(), "1" | "true" | "yes" | "on")
}

/// Ruta del fichero del token de emparejamiento (`BRIDGE_TOKEN_FILE`, por defecto junto al cwd).
fn token_file_path() -> PathBuf {
    std::env::var(ENV_TOKEN_FILE)
        .map(PathBuf::from)
        .unwrap_or_else(|_| PathBuf::from(DEFAULT_TOKEN_FILE))
}

/// Política **fija** de claims del bridge-token: `aud = "erplora-bridge"` **siempre** (constante del
/// protocolo, no configurable) y `hub_id` **no fijado** (el Bridge es genérico, no está vinculado a un
/// hub). El `aud` es la frontera de seguridad — un token de usuario/máquina no lo lleva; el `hub_id`
/// del token es informativo. Compartida por el override de env y el fetch al SaaS para que la
/// verificación sea idéntica venga la clave de donde venga.
fn bridge_jwt_policy() -> (Option<String>, Option<String>) {
    (Some(BRIDGE_AUDIENCE.to_string()), None)
}

/// Verificador de JWT desde una clave pública **inyectada por env** (override/offline): inline
/// (`BRIDGE_JWT_PUBLIC_KEY`) o fichero (`BRIDGE_JWT_PUBLIC_KEY_FILE`). `None` si no se configuró.
/// La fuente PRIMARIA de la clave es el SaaS ([`jwt_verifier_from_saas`]); esto es el escape.
fn jwt_from_env() -> Option<JwtVerifier> {
    let pem = std::env::var(ENV_JWT_PUBLIC_KEY).ok().or_else(|| {
        std::env::var(ENV_JWT_PUBLIC_KEY_FILE)
            .ok()
            .and_then(|p| std::fs::read_to_string(p).ok())
    })?;
    let pem = pem.trim();
    if pem.is_empty() {
        return None;
    }
    let (aud, hub_id) = bridge_jwt_policy();
    match JwtVerifier::from_rsa_pem(pem, aud, hub_id) {
        Ok(v) => {
            tracing::info!("Bridge: verificación JWT por clave pública (override de env) activada");
            Some(v)
        }
        Err(e) => {
            tracing::warn!(error = %e, "Bridge: {ENV_JWT_PUBLIC_KEY} inválida; se ignora la vía JWT");
            None
        }
    }
}

/// **Fuente primaria de la clave pública**: la pide al SaaS (`GET {saas}/api/v1/auth/public-key/`,
/// mismo endpoint y forma que consume el runtime del Hub) y construye el verificador con la política
/// fija ([`bridge_jwt_policy`]: `aud=erplora-bridge`, `hub_id` no fijado). `None` si el SaaS no
/// responde o la clave no es válida — el Bridge degrada a la vía simétrica (no aborta). El SaaS
/// gestiona la rotación de la clave.
pub async fn jwt_verifier_from_saas(saas_url: &str) -> Option<JwtVerifier> {
    let pem = fetch_saas_public_key(saas_url).await?;
    let (aud, hub_id) = bridge_jwt_policy();
    match JwtVerifier::from_rsa_pem(&pem, aud, hub_id) {
        Ok(v) => {
            tracing::info!("Bridge: clave pública obtenida del SaaS; verificación JWT activada");
            Some(v)
        }
        Err(e) => {
            tracing::warn!(error = %e, "Bridge: la clave pública del SaaS no es válida; se ignora");
            None
        }
    }
}

/// `GET {saas}/api/v1/auth/public-key/` → `{ "public_key": "<PEM>", "algorithm": "RS256" }`. Timeout
/// ACOTADO (corre en el arranque, antes de escuchar): una red hostil no debe colgar el Bridge.
async fn fetch_saas_public_key(saas_url: &str) -> Option<String> {
    let url = format!("{}/api/v1/auth/public-key/", saas_url.trim_end_matches('/'));
    let client = reqwest::Client::builder()
        .connect_timeout(std::time::Duration::from_secs(3))
        .timeout(std::time::Duration::from_secs(5))
        .build()
        .ok()?;
    let resp = client.get(&url).send().await.ok()?;
    if !resp.status().is_success() {
        return None;
    }
    let v: serde_json::Value = resp.json().await.ok()?;
    v.get("public_key")
        .and_then(|k| k.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
}

/// Resuelve el token (fail-closed): `env_token` inyectado → fichero persistido → genera+persiste y
/// muestra el código de emparejamiento. **Siempre** devuelve un token no vacío. Pura respecto al
/// entorno (recibe el valor de env y la ruta) para poder testearla sin tocar variables globales.
fn resolve_token(env_token: Option<String>, path: &Path) -> String {
    // 1. Token inyectado (ECS/empaquetado).
    if let Some(t) = env_token {
        let t = t.trim();
        if !t.is_empty() {
            return t.to_string();
        }
    }
    // 2. Token persistido de un emparejamiento anterior.
    if let Ok(contents) = std::fs::read_to_string(path) {
        let t = contents.trim();
        if !t.is_empty() {
            return t.to_string();
        }
    }
    // 3. Primer arranque sin token: genera, persiste y muestra el código de emparejamiento.
    let token = generate_token();
    persist_token(path, &token);
    log_pairing_code(&token);
    token
}

/// Token aleatorio = dos uuid v4 concatenados (≈244 bits de entropía, CSPRNG vía getrandom).
fn generate_token() -> String {
    format!(
        "{}{}",
        uuid::Uuid::new_v4().simple(),
        uuid::Uuid::new_v4().simple()
    )
}

/// Persiste el token (best-effort). En unix restringe los permisos a `0600` (solo el dueño).
/// Si falla la escritura, loggea un `warn`: el token se regenerará en el próximo arranque.
fn persist_token(path: &Path, token: &str) {
    match std::fs::write(path, token) {
        Ok(()) => {
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                let _ = std::fs::set_permissions(path, std::fs::Permissions::from_mode(0o600));
            }
            tracing::info!(path = %path.display(), "Bridge: token de emparejamiento generado y guardado");
        }
        Err(e) => tracing::warn!(
            error = %e,
            path = %path.display(),
            "Bridge: no pude persistir el token; se regenerará en el próximo arranque",
        ),
    }
}

/// Muestra **una vez** el código de emparejamiento en la consola del operador. Es el único punto
/// donde el secreto se imprime (canal local, máquina del propio usuario); nunca en validación.
fn log_pairing_code(token: &str) {
    tracing::info!(
        "\n┌─ Bridge · código de emparejamiento ────────────────────────────\n\
         │  {token}\n\
         │  Introdúcelo en Ajustes → Bridge de la app para conectar el hardware.\n\
         └─────────────────────────────────────────────────────────────────"
    );
}

/// Orígenes implícitamente de confianza, sin necesidad de configuración:
///   - cualquier `http`/`https`/`ws`/`wss` a `localhost` / `127.0.0.1` / `[::1]` (cualquier puerto),
///   - el esquema del shell Tauri (`tauri://…`),
///   - `null` queda explícitamente fuera (lo filtra el llamador).
fn is_builtin_trusted_origin(origin: &str) -> bool {
    // Esquema del shell Tauri (Tauri v2 usa `tauri://localhost` y, en Windows, `https://tauri.localhost`).
    if origin.starts_with("tauri://") {
        return true;
    }

    // Parsea `scheme://host[:port]` a mano (sin dependencia de URL). `Uri` de http exige path para
    // algunos esquemas, así que extraemos el host nosotros.
    let Some((scheme, rest)) = origin.split_once("://") else {
        return false;
    };
    if !matches!(scheme, "http" | "https" | "ws" | "wss") {
        return false;
    }
    // `rest` = `host[:port][/path]`; nos quedamos con el host.
    let host_port = rest.split('/').next().unwrap_or(rest);
    // IPv6 entre corchetes: `[::1]:port`.
    let host = if let Some(stripped) = host_port.strip_prefix('[') {
        // hasta el ']'
        stripped.split(']').next().unwrap_or(stripped)
    } else {
        host_port.split(':').next().unwrap_or(host_port)
    };

    matches!(host, "localhost" | "127.0.0.1" | "::1")
        || host.eq_ignore_ascii_case("tauri.localhost")
}

/// `true` si un `host[:port]` (cabecera `Host`, sin esquema) es loopback. Extrae el host (maneja
/// `[::1]:port`) y lo casa contra `localhost`/`127.0.0.1`/`::1`.
fn is_loopback_host(host_port: &str) -> bool {
    let host = if let Some(stripped) = host_port.strip_prefix('[') {
        stripped.split(']').next().unwrap_or(stripped) // IPv6: `[::1]:port`
    } else {
        host_port.split(':').next().unwrap_or(host_port)
    };
    matches!(host, "localhost" | "127.0.0.1" | "::1")
}

/// Extrae el token presentado, en orden de preferencia:
///   1. `Authorization: Bearer <token>`
///   2. `X-Hub-Session: <token>`
///   3. query param `?token=<token>` (única vía que tiene un `WebSocket` de navegador)
fn presented_token(headers: &HeaderMap, uri: &Uri) -> Option<String> {
    if let Some(auth) = headers
        .get(axum::http::header::AUTHORIZATION)
        .and_then(|v| v.to_str().ok())
    {
        if let Some(bearer) = auth.strip_prefix("Bearer ").or_else(|| auth.strip_prefix("bearer ")) {
            let bearer = bearer.trim();
            if !bearer.is_empty() {
                return Some(bearer.to_string());
            }
        }
    }

    if let Some(sess) = headers.get(SESSION_HEADER).and_then(|v| v.to_str().ok()) {
        let sess = sess.trim();
        if !sess.is_empty() {
            return Some(sess.to_string());
        }
    }

    // Query param `token`.
    if let Some(query) = uri.query() {
        for pair in query.split('&') {
            if let Some(value) = pair.strip_prefix("token=") {
                let decoded = percent_decode(value);
                if !decoded.is_empty() {
                    return Some(decoded);
                }
            }
        }
    }

    None
}

/// Decodifica un valor de query mínimamente (`%XX` y `+`). Evita arrastrar una dependencia solo
/// para esto; el token es opaco (hex/base64-url), rara vez necesita escaping, pero por robustez.
fn percent_decode(s: &str) -> String {
    let bytes = s.as_bytes();
    let mut out = Vec::with_capacity(bytes.len());
    let mut i = 0;
    while i < bytes.len() {
        match bytes[i] {
            b'%' if i + 2 < bytes.len() => {
                let hi = (bytes[i + 1] as char).to_digit(16);
                let lo = (bytes[i + 2] as char).to_digit(16);
                if let (Some(hi), Some(lo)) = (hi, lo) {
                    out.push((hi * 16 + lo) as u8);
                    i += 3;
                    continue;
                }
                out.push(b'%');
                i += 1;
            }
            b'+' => {
                out.push(b' ');
                i += 1;
            }
            b => {
                out.push(b);
                i += 1;
            }
        }
    }
    String::from_utf8_lossy(&out).into_owned()
}

/// Comparación en tiempo constante (evita timing oracle al validar el secreto). Independiente de
/// la longitud: compara siempre el mismo número de bytes que el más largo.
fn constant_time_eq(a: &[u8], b: &[u8]) -> bool {
    let max = a.len().max(b.len());
    let mut diff = (a.len() ^ b.len()) as u8;
    for i in 0..max {
        let x = a.get(i).copied().unwrap_or(0);
        let y = b.get(i).copied().unwrap_or(0);
        diff |= x ^ y;
    }
    diff == 0
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{header, HeaderValue};

    fn headers_with(pairs: &[(&str, &str)]) -> HeaderMap {
        let mut h = HeaderMap::new();
        for (k, v) in pairs {
            h.insert(
                axum::http::HeaderName::from_bytes(k.as_bytes()).unwrap(),
                HeaderValue::from_str(v).unwrap(),
            );
        }
        h
    }

    fn uri(path_and_query: &str) -> Uri {
        path_and_query.parse().unwrap()
    }

    // ── Host allowlist (anti DNS-rebinding) ──────────────────────────────────

    #[test]
    fn host_loopback_variants_allowed() {
        let auth = BridgeAuth::new(None, vec![]);
        for h in ["localhost:12321", "127.0.0.1:12321", "localhost", "127.0.0.1", "[::1]:12321"] {
            let hm = headers_with(&[(header::HOST.as_str(), h)]);
            assert!(auth.host_allowed(&hm), "{h} debería estar permitido");
        }
    }

    #[test]
    fn host_rebinding_domain_rejected() {
        let auth = BridgeAuth::new(None, vec![]);
        for h in ["attacker.com", "attacker.com:12321", "erp.midominio.com", "192.168.1.50:12321"] {
            let hm = headers_with(&[(header::HOST.as_str(), h)]);
            assert!(!auth.host_allowed(&hm), "{h} NO debería estar permitido (rebinding)");
        }
    }

    #[test]
    fn host_absent_allowed_for_native_clients() {
        let auth = BridgeAuth::new(None, vec![]);
        assert!(auth.host_allowed(&HeaderMap::new()));
    }

    // ── Origin allowlist ───────────────────────────────────────────────────

    #[test]
    fn origin_loopback_variants_allowed() {
        let auth = BridgeAuth::new(None, vec![]);
        for o in [
            "http://localhost",
            "http://localhost:5173",
            "https://localhost",
            "http://127.0.0.1:8787",
            "ws://127.0.0.1:12321",
            "https://tauri.localhost",
            "http://[::1]:3000",
        ] {
            assert!(auth.origin_allowed(Some(o)), "{o} debería estar permitido");
        }
    }

    #[test]
    fn origin_tauri_scheme_allowed() {
        let auth = BridgeAuth::new(None, vec![]);
        assert!(auth.origin_allowed(Some("tauri://localhost")));
    }

    #[test]
    fn origin_absent_allowed_for_native_clients() {
        let auth = BridgeAuth::new(None, vec![]);
        assert!(auth.origin_allowed(None));
    }

    #[test]
    fn origin_null_rejected() {
        let auth = BridgeAuth::new(None, vec![]);
        assert!(!auth.origin_allowed(Some("null")));
    }

    #[test]
    fn origin_third_party_rejected() {
        let auth = BridgeAuth::new(None, vec![]);
        for o in [
            "https://evil.example.com",
            "http://localhost.evil.com",       // truco de subdominio
            "https://notlocalhost",
            "http://192.168.1.50",             // LAN, no loopback
        ] {
            assert!(!auth.origin_allowed(Some(o)), "{o} NO debería estar permitido");
        }
    }

    #[test]
    fn origin_extra_configured_allowed() {
        let auth = BridgeAuth::new(None, vec!["https://app.erplora.com".into()]);
        assert!(auth.origin_allowed(Some("https://app.erplora.com")));
        assert!(auth.origin_allowed(Some("https://APP.erplora.com"))); // case-insensitive
        assert!(!auth.origin_allowed(Some("https://other.erplora.com")));
    }

    // ── Token validation ───────────────────────────────────────────────────

    #[test]
    fn token_disabled_when_unset() {
        let auth = BridgeAuth::new(None, vec![]);
        // Sin secreto, cualquier handshake con buen Origin pasa.
        assert!(auth.token_valid(&HeaderMap::new(), &uri("/ws")));
        assert!(!auth.token_required());
    }

    #[test]
    fn token_absent_is_unauthorized_when_required() {
        let auth = BridgeAuth::new(Some("s3cr3t".into()), vec![]);
        assert!(!auth.token_valid(&HeaderMap::new(), &uri("/ws")));
    }

    #[test]
    fn token_invalid_is_rejected() {
        let auth = BridgeAuth::new(Some("s3cr3t".into()), vec![]);
        let h = headers_with(&[(header::AUTHORIZATION.as_str(), "Bearer wrong")]);
        assert!(!auth.token_valid(&h, &uri("/ws")));
        let h2 = headers_with(&[(SESSION_HEADER, "wrong")]);
        assert!(!auth.token_valid(&h2, &uri("/ws")));
        assert!(!auth.token_valid(&HeaderMap::new(), &uri("/ws?token=wrong")));
    }

    #[test]
    fn token_valid_via_bearer() {
        let auth = BridgeAuth::new(Some("s3cr3t".into()), vec![]);
        let h = headers_with(&[(header::AUTHORIZATION.as_str(), "Bearer s3cr3t")]);
        assert!(auth.token_valid(&h, &uri("/ws")));
    }

    #[test]
    fn token_valid_via_session_header() {
        let auth = BridgeAuth::new(Some("s3cr3t".into()), vec![]);
        let h = headers_with(&[(SESSION_HEADER, "s3cr3t")]);
        assert!(auth.token_valid(&h, &uri("/ws")));
    }

    #[test]
    fn token_valid_via_query_param() {
        let auth = BridgeAuth::new(Some("s3cr3t".into()), vec![]);
        assert!(auth.token_valid(&HeaderMap::new(), &uri("/ws?token=s3cr3t")));
        // Con otros params alrededor.
        assert!(auth.token_valid(&HeaderMap::new(), &uri("/ws?foo=1&token=s3cr3t&bar=2")));
    }

    #[test]
    fn token_query_percent_decoded() {
        let auth = BridgeAuth::new(Some("a b+c".into()), vec![]);
        // `a b+c` codificado: espacio=%20, '+' literal=%2B.
        assert!(auth.token_valid(&HeaderMap::new(), &uri("/ws?token=a%20b%2Bc")));
    }

    // ── evaluate(): orden Origin → token ─────────────────────────────────────

    #[test]
    fn evaluate_allows_good_origin_and_token() {
        let auth = BridgeAuth::new(Some("s3cr3t".into()), vec![]);
        let h = headers_with(&[
            (header::ORIGIN.as_str(), "http://localhost:5173"),
            (header::AUTHORIZATION.as_str(), "Bearer s3cr3t"),
        ]);
        assert_eq!(auth.evaluate(&h, &uri("/ws")), AuthOutcome::Allowed);
    }

    #[test]
    fn evaluate_rejects_bad_origin_before_checking_token() {
        let auth = BridgeAuth::new(Some("s3cr3t".into()), vec![]);
        // Buen token pero mal origen → 403 (la barrera de origen va primero).
        let h = headers_with(&[
            (header::ORIGIN.as_str(), "https://evil.example.com"),
            (header::AUTHORIZATION.as_str(), "Bearer s3cr3t"),
        ]);
        assert_eq!(auth.evaluate(&h, &uri("/ws")), AuthOutcome::ForbiddenOrigin);
        assert_eq!(auth.evaluate(&h, &uri("/ws")).status_code(), axum::http::StatusCode::FORBIDDEN);
    }

    #[test]
    fn evaluate_rejects_missing_token_with_good_origin() {
        let auth = BridgeAuth::new(Some("s3cr3t".into()), vec![]);
        let h = headers_with(&[(header::ORIGIN.as_str(), "http://localhost:5173")]);
        assert_eq!(auth.evaluate(&h, &uri("/ws")), AuthOutcome::Unauthorized);
        assert_eq!(auth.evaluate(&h, &uri("/ws")).status_code(), axum::http::StatusCode::UNAUTHORIZED);
    }

    #[test]
    fn evaluate_native_client_no_origin_with_token() {
        // Cliente sin Origin (sidecar/native) pero con token correcto → permitido.
        let auth = BridgeAuth::new(Some("s3cr3t".into()), vec![]);
        let h = headers_with(&[(SESSION_HEADER, "s3cr3t")]);
        assert_eq!(auth.evaluate(&h, &uri("/ws")), AuthOutcome::Allowed);
    }

    #[test]
    fn constant_time_eq_basic() {
        assert!(constant_time_eq(b"abc", b"abc"));
        assert!(!constant_time_eq(b"abc", b"abd"));
        assert!(!constant_time_eq(b"abc", b"ab"));
        assert!(!constant_time_eq(b"", b"x"));
        assert!(constant_time_eq(b"", b""));
    }

    // ── token: dev mode + resolución/persistencia (emparejamiento) ───────────

    /// Ruta temporal única por test (uuid) para no pisarse entre tests en paralelo.
    fn tmp_token_path() -> PathBuf {
        std::env::temp_dir().join(format!("bridge-token-test-{}", uuid::Uuid::new_v4()))
    }

    #[test]
    fn is_truthy_values() {
        for v in ["1", "true", "TRUE", "yes", "on", " On "] {
            assert!(is_truthy(v), "{v:?} debería ser truthy");
        }
        for v in ["0", "false", "no", "off", "", "x"] {
            assert!(!is_truthy(v), "{v:?} NO debería ser truthy");
        }
    }

    #[test]
    fn resolve_token_prefers_injected_env() {
        let p = tmp_token_path();
        let t = resolve_token(Some("  injected-secret  ".into()), &p);
        assert_eq!(t, "injected-secret", "el token inyectado gana y se trimea");
        assert!(!p.exists(), "con token inyectado NO se escribe fichero de emparejamiento");
    }

    #[test]
    fn resolve_token_generates_persists_then_reuses() {
        let p = tmp_token_path();
        // 1er arranque sin token: genera y persiste.
        let t1 = resolve_token(None, &p);
        assert!(t1.len() >= 32, "token generado suficientemente largo (fue {})", t1.len());
        assert!(p.exists(), "el token de emparejamiento se persiste");
        // 2º arranque: reutiliza el mismo del fichero (emparejamiento estable entre reinicios).
        let t2 = resolve_token(None, &p);
        assert_eq!(t1, t2, "el token persistido se reutiliza entre arranques");
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn resolve_token_ignores_blank_env_and_blank_file() {
        let p = tmp_token_path();
        std::fs::write(&p, "   \n").unwrap(); // fichero en blanco
        let t = resolve_token(Some("   ".into()), &p); // env en blanco
        assert!(!t.trim().is_empty(), "ni env ni fichero en blanco valen → genera uno nuevo");
        assert_eq!(
            std::fs::read_to_string(&p).unwrap().trim(),
            t,
            "el token nuevo sobrescribe el fichero en blanco",
        );
        let _ = std::fs::remove_file(&p);
    }

    #[test]
    fn generated_tokens_are_unique() {
        assert_ne!(generate_token(), generate_token(), "cada token generado es distinto");
    }

    // ── Credencial JWT firmada (RS256, clave pública) ────────────────────────
    // Keypairs SOLO de test (no son secretos reales). `TEST_*` es el par bueno; `OTHER_PRIV` firma
    // tokens con la clave equivocada para probar el rechazo por firma.

    use jsonwebtoken::{encode, EncodingKey, Header};
    use std::time::{SystemTime, UNIX_EPOCH};

    const TEST_PUB: &str = r#"-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEArkiU7mt7J8B9U/qh0095
XRLb5kY0QUVsqM2F2bJdWEOQIbWXlsPK3NtlVzB7xWp0+9x79N3dTtt5jdis9gmA
Ko8bt5v077MG8jDhiC57N1asU3gJTwG/q1OsY1XHfUwUnqqdOiQe7TQH5P0DUcQW
N7WnzVaISULpDSq+bEOt4tYEc2hEMcKJarZM/I2/E3Q/EPKb8bkzTA5bvuIFJG05
UtILoZTJaa8kLePIsBgWed2zdubWIFUlTHrbmI7PTGZjKhEbKgf1JXuV79IzFe+0
YY04dT3HV8ZNM8d+qJ9MMsBNvthXsV5hn29Q2sb5J0Mfwcxzw17gFDSfRN0DxedN
jQIDAQAB
-----END PUBLIC KEY-----"#;

    const TEST_PRIV: &str = r#"-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCuSJTua3snwH1T
+qHTT3ldEtvmRjRBRWyozYXZsl1YQ5AhtZeWw8rc22VXMHvFanT73Hv03d1O23mN
2Kz2CYAqjxu3m/TvswbyMOGILns3VqxTeAlPAb+rU6xjVcd9TBSeqp06JB7tNAfk
/QNRxBY3tafNVohJQukNKr5sQ63i1gRzaEQxwolqtkz8jb8TdD8Q8pvxuTNMDlu+
4gUkbTlS0guhlMlpryQt48iwGBZ53bN25tYgVSVMetuYjs9MZmMqERsqB/Ule5Xv
0jMV77RhjTh1PcdXxk0zx36on0wywE2+2FexXmGfb1DaxvknQx/BzHPDXuAUNJ9E
3QPF502NAgMBAAECggEAK90zsrAVfoNJZ84AVa0+d+jrtJC9zSG6f9++TPTB3pme
mIVaQkVD9QM5BdE7jYvGJq+u+QmwDg1aEhPTMFdizRNYoAUeCAgwettHoB1GwL5N
P/LJsPtZMLct/5BS1ZvE4sxBJyV5LS03wW/Wmok2KE5NjfY19e5jtn8oDxqXlKvr
dAbMAGCQHunxZtZKQS9Er5ny8WP2z9v1zcRHlqdEukDqrzdLKdOUvpuRpt2ZoDAj
TsvwsFfZ99vWvJb4F1scZp8/16BT19tLg4S9YPUe7wmGBALGQqE9z6T9TvLmlime
ITdm2S1Hjwy8puWCuuiIvowo7PXgrO77IBl2lBYKxwKBgQDZLSCKsGdb8THljof3
gp8YZ5KZ0tRa0yHs5EuU6stRUK3weoBsBQ3iZPfqpMonYjUkuFLJ09KrK6hQqfU8
nn0LpA7ST3w+DpWS+P5rqN4STnLM1mGv4EzCx1oM/rYJi588umxxlCfO6TVDgXNh
1EmABmfBXwewLiqO+LifC0VCtwKBgQDNcIHRF+7wXR8s8eFaF/HHv8TN6a0Z6KZx
C+T5NWPNtXXsI7hA6VMsUTtD66uLgHSQh8G1hTRto4udA6pg8H2UjbRleaBfi1B1
sXx8jY2Mj52c5aS3/LV/JFyq0XocauRA2IGYZRX4D+wBS5qiKJe+HpnK06vBV608
VcljJSud2wKBgQCQX0aFzBU58tJ3x1Ot/4Ch6aB0b8pJgpfH8lAodBmrOdYXymf6
5zU+rl589wWIPuoTOhGXKCChN8mRrhpgLP/1sB9GQh7W5j0a0jnX+g9+3fXFJDMW
hyagSYQcpWsAV3gJF+klbBc2nqOQ98prW4Ns/1UUIIds4JPcLY4V9JkbawKBgQCd
HJWrGuqY2B6neLQm+njlkjsoXrULQ2lGuxn5nGMfRs9QMGERA1+gXN8+KlWe8jYy
8h+qepyF3LVA9zStvj3MBjMYB9QmPZzi5UGW34qJHKwk+VrnelQzT9Our1T7tqOp
E+rIaUZL16FdvDweF3004KItA4Qu8KaDpffF4v9gUQKBgAX7P75RT6fWXc4fR3Yk
w+ZQHCx2l47R2VzfllIO09RLShHkp/oRVSnpieU2gcXpJp51J5Gps5Bl2kxI+h3K
ab8zNM0IaM8M2WpgVwVN5mMCNUb/Qo107pvDOKe2MdlW4+RgOd0tjFG+XS8We3pf
xytPSgjzk/vei8IeqVZ5N+5T
-----END PRIVATE KEY-----"#;

    const OTHER_PRIV: &str = r#"-----BEGIN PRIVATE KEY-----
MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgwggSkAgEAAoIBAQCXep+uaSIf7icW
PcBja/zFHTgPeJS4BvPA/zK9epfwlXGqYY7ULsm683qTSvgsAyF3S1upDpbOOGNJ
v+EOdCTwuWlOb1roh0+Vb8eqVArc/WTqmuoN1uKJ0VzG/0jx3ooGeBYW13zzL3Q2
1yQsWdNPUN2RYLB2HI2rcGiMv5XU/r26Dms/OHMAnyvEI6ebniXfwahhkhcbvzya
pQxKqcX1TSEDMvKj9Zie7rpOReTEPMX3vn4QWPLeXWlU87kHtDvDnDYMQmQgelsu
Y3OeWNnoNInAPtMnx13ElGEtXTbKcSicdKbjWBIsb3tBtUahpVBdhhduYu44oa0z
Gyxv2q51AgMBAAECggEANCo1XVG1P7u62Czx2QsyJAt459MFnA5A2SDJL3lNY7uD
RkKMdkOakvgQKTMzHa0CVFuuOBzfECtY/efHMDwNEJ05R5qPeu5GGNdCskR47TuS
CjzJB3UN1Jo10g3N6AVUEQA/0yPoUrLv2YbjXSad332gn9TlT/drTjPKvVWo2o1L
qpoMt1q5mTghzy+g2HTRapEW+mzxMfx9jJpz2idtdSaqdsWixRGuAb5DJHsLirhC
GiThzxkTpdlL1ujiryiSgTD2tEdhsQ5PAVh+A9IRWRLAP2OB4MW7rxsK98HT5lEX
BIW2hyY1NUhvqlrCIXCSB0PY85dn2pSPOtFmVvuH7QKBgQDO9o3vYzuf80e6dIQr
4yh6FvIjlPwY2T4cNkwBG0CZUf9Vwgm73H5wGWOyqAo7vl94zvC4ihL4D8pPqRen
Yr+hcr8qNNU8XeXfIbMSESSWAQDKagvFi8dP4+MXJzXw9sv3mOjOvus/bld9/zhN
TAWO6UAjChKKq7oUAwsVrWx4VwKBgQC7XqeRc6k9CqrtPa9LiNh4Tjid4k8DV54F
vCGYDuvchAqLtMSEHnjzGkrDBAx+7oXZVN8arTQskcnEBJ8mex6e/esOWHaat2Jt
YCrzCINNIn2nmwgPaOSiDZRxbo5/dXbrausC7ftSOIub57pkCScpu3DLcEystn6n
uaVt0AhAEwKBgQC1O2hNAZub1GCyYQfAmrm+N8uv5u3fIJVoBRAHRAMMf6ZVRYZa
kJnTthf8wXO8n1dhJe3b22UC/mjN2yeQd0ORsDbAUeWMaDk8bHkvz/02sggsODK4
uU8+oTMh+j8dFDDGT4tGSB8eu5Q4DD8USQbw/0YfqNlVv01B6uxQ/j1nHwKBgQCM
QmAH1uASbMDlFS76yTbaYBurvLRPGTCWtG0lac4P5dwLFseg6zq5KK5ca9R61Ezo
EstsKcoLrxqtnJQSd0nF1Og3detbB/orTDj6cx3vCOmtJLWU631y/d1oSE1thl39
/qxsJf/jXabMj1wM9HkXmVPnRmpvQ7FuFt+KY5c5dwKBgBRcpQ+4bGqEDr6Duo91
9KXCeCrFOZLHKO1ttisODHwD+7oDux+WjKjzndGp0QcmQ00TAkZISl0QGjQJ2SMq
q8VD3AmaG1QetOaoFE3a0njqjcM/5WUd1xh7tt5d6/lkjshROjYI6vOWcRRcSjal
IvFItyUYMXiE4CEIlmhbskGV
-----END PRIVATE KEY-----"#;

    /// Timestamp Unix (segundos) + `delta`.
    fn ts(delta: i64) -> i64 {
        let now = SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_secs() as i64;
        now + delta
    }

    /// Firma un JWT RS256 con `priv_pem` a partir de unos claims JSON.
    fn mint(claims: serde_json::Value, priv_pem: &str) -> String {
        let key = EncodingKey::from_rsa_pem(priv_pem.as_bytes()).expect("priv pem");
        encode(&Header::new(Algorithm::RS256), &claims, &key).expect("encode")
    }

    fn verifier(aud: Option<&str>, hub_id: Option<&str>) -> JwtVerifier {
        JwtVerifier::from_rsa_pem(TEST_PUB, aud.map(Into::into), hub_id.map(Into::into))
            .expect("test pub key")
    }

    #[test]
    fn jwt_verify_valid_and_tampered() {
        let v = verifier(None, None);
        let tok = mint(serde_json::json!({ "exp": ts(300) }), TEST_PRIV);
        assert!(v.verify(&tok), "un JWT bien firmado y no expirado verifica");
        // Alterar un carácter del payload invalida la firma.
        let mut bad = tok.clone();
        let mid = bad.len() / 2;
        bad.replace_range(mid..mid + 1, if &bad[mid..mid + 1] == "a" { "b" } else { "a" });
        assert!(!v.verify(&bad), "un JWT manipulado NO verifica");
    }

    #[test]
    fn jwt_valid_token_authorizes_from_any_origin() {
        // Solo-JWT (sin token simétrico). Un token válido autoriza incluso desde el dominio propio
        // del tenant, que NO está en ninguna allowlist — la firma ES la prueba (agnóstico al dominio).
        let auth = BridgeAuth::new(None, vec![]).with_jwt(verifier(None, None));
        let tok = mint(serde_json::json!({ "exp": ts(300) }), TEST_PRIV);
        let h = headers_with(&[(header::ORIGIN.as_str(), "https://erp.midominio.com")]);
        assert_eq!(auth.evaluate(&h, &uri(&format!("/ws?token={tok}"))), AuthOutcome::Allowed);
    }

    #[test]
    fn jwt_expired_is_rejected() {
        let auth = BridgeAuth::new(None, vec![]).with_jwt(verifier(None, None));
        // Caducado holgadamente más allá del leeway por defecto de `jsonwebtoken` (60s, skew de reloj).
        let tok = mint(serde_json::json!({ "exp": ts(-120) }), TEST_PRIV);
        let h = headers_with(&[(header::ORIGIN.as_str(), "https://erp.midominio.com")]);
        assert_eq!(auth.evaluate(&h, &uri(&format!("/ws?token={tok}"))), AuthOutcome::Unauthorized);
    }

    #[test]
    fn jwt_bad_signature_is_rejected() {
        // Firmado con la clave EQUIVOCADA → la clave pública del Bridge no lo valida.
        let auth = BridgeAuth::new(None, vec![]).with_jwt(verifier(None, None));
        let tok = mint(serde_json::json!({ "exp": ts(300) }), OTHER_PRIV);
        let h = headers_with(&[(header::ORIGIN.as_str(), "https://erp.midominio.com")]);
        assert_eq!(auth.evaluate(&h, &uri(&format!("/ws?token={tok}"))), AuthOutcome::Unauthorized);
    }

    #[test]
    fn jwt_hub_id_must_match_when_configured() {
        let auth = BridgeAuth::new(None, vec![]).with_jwt(verifier(None, Some("hub-1")));
        let ok = mint(serde_json::json!({ "exp": ts(300), "hub_id": "hub-1" }), TEST_PRIV);
        let bad = mint(serde_json::json!({ "exp": ts(300), "hub_id": "hub-2" }), TEST_PRIV);
        let h = headers_with(&[(header::ORIGIN.as_str(), "https://erp.midominio.com")]);
        assert_eq!(auth.evaluate(&h, &uri(&format!("/ws?token={ok}"))), AuthOutcome::Allowed);
        assert_eq!(auth.evaluate(&h, &uri(&format!("/ws?token={bad}"))), AuthOutcome::Unauthorized);
    }

    #[test]
    fn jwt_aud_must_match_when_configured() {
        let auth = BridgeAuth::new(None, vec![]).with_jwt(verifier(Some("erplora-bridge"), None));
        let ok = mint(serde_json::json!({ "exp": ts(300), "aud": "erplora-bridge" }), TEST_PRIV);
        let bad = mint(serde_json::json!({ "exp": ts(300), "aud": "otro" }), TEST_PRIV);
        let h = headers_with(&[(header::ORIGIN.as_str(), "https://erp.midominio.com")]);
        assert_eq!(auth.evaluate(&h, &uri(&format!("/ws?token={ok}"))), AuthOutcome::Allowed);
        assert_eq!(auth.evaluate(&h, &uri(&format!("/ws?token={bad}"))), AuthOutcome::Unauthorized);
    }

    #[test]
    fn jwt_without_aud_is_rejected_when_aud_expected() {
        // Un token SIN claim `aud` NO debe colar cuando se exige audience. Si no, un token de
        // MÁQUINA o de USUARIO (que no llevan `aud`) con el `hub_id` correcto autorizaría el
        // hardware — justo lo que el audience dedicado debe impedir. `jsonwebtoken` no exige `aud`
        // por defecto (solo lo valida si está presente); hay que forzarlo como claim requerido.
        let auth = BridgeAuth::new(None, vec![]).with_jwt(verifier(Some("erplora-bridge"), Some("hub-1")));
        // Simula un token de máquina: hub_id correcto, exp válido, pero SIN aud.
        let machine_like = mint(serde_json::json!({ "exp": ts(300), "hub_id": "hub-1" }), TEST_PRIV);
        let h = headers_with(&[(header::ORIGIN.as_str(), "https://erp.midominio.com")]);
        assert_eq!(
            auth.evaluate(&h, &uri(&format!("/ws?token={machine_like}"))),
            AuthOutcome::Unauthorized
        );
    }

    #[test]
    fn jwt_and_symmetric_token_coexist() {
        // Con ambas vías: el JWT vale desde cualquier origin; el simétrico exige origin de confianza.
        let auth = BridgeAuth::new(Some("s3cr3t".into()), vec![]).with_jwt(verifier(None, None));
        let jwt = mint(serde_json::json!({ "exp": ts(300) }), TEST_PRIV);

        // JWT válido desde dominio foráneo → Allowed.
        let h_jwt = headers_with(&[(header::ORIGIN.as_str(), "https://erp.midominio.com")]);
        assert_eq!(auth.evaluate(&h_jwt, &uri(&format!("/ws?token={jwt}"))), AuthOutcome::Allowed);

        // Token simétrico desde loopback → Allowed.
        let h_sym_ok = headers_with(&[
            (header::ORIGIN.as_str(), "http://localhost:5173"),
            (header::AUTHORIZATION.as_str(), "Bearer s3cr3t"),
        ]);
        assert_eq!(auth.evaluate(&h_sym_ok, &uri("/ws")), AuthOutcome::Allowed);

        // Token simétrico desde dominio foráneo → ForbiddenOrigin (el simétrico NO es agnóstico).
        let h_sym_bad = headers_with(&[
            (header::ORIGIN.as_str(), "https://erp.midominio.com"),
            (header::AUTHORIZATION.as_str(), "Bearer s3cr3t"),
        ]);
        assert_eq!(auth.evaluate(&h_sym_bad, &uri("/ws")), AuthOutcome::ForbiddenOrigin);
    }
}
