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

/// Política de autenticación del Bridge. Inmutable tras construirse desde el entorno.
#[derive(Debug, Clone)]
pub struct BridgeAuth {
    /// Secreto compartido; `None` desactiva la barrera de token (dev/local).
    token: Option<String>,
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
            return Self { token: None, extra_origins };
        }

        let env_token = std::env::var(ENV_TOKEN).ok();
        let token = resolve_token(env_token, &token_file_path());
        Self { token: Some(token), extra_origins }
    }

    /// Constructor explícito (tests / arranque programático del sidecar Tauri, que construirá la
    /// política sin pasar por el entorno). El binario standalone usa `from_env`.
    #[allow(dead_code)] // API pública: la consume el sidecar Tauri (futuro) y los tests.
    pub fn new(token: Option<String>, extra_origins: Vec<String>) -> Self {
        Self { token, extra_origins }
    }

    /// `true` si la barrera de token está activa (hay secreto configurado). Útil para que el
    /// consumidor decida si advertir/abortar en arranque fail-closed.
    #[allow(dead_code)] // API pública consumida por tests / arranque programático.
    pub fn token_required(&self) -> bool {
        self.token.is_some()
    }

    /// Evalúa un handshake completo: primero `Origin`, luego token. Devuelve el primer fallo.
    pub fn evaluate(&self, headers: &HeaderMap, uri: &Uri) -> AuthOutcome {
        let origin = headers
            .get(axum::http::header::ORIGIN)
            .and_then(|v| v.to_str().ok());
        if !self.origin_allowed(origin) {
            return AuthOutcome::ForbiddenOrigin;
        }
        if !self.token_valid(headers, uri) {
            return AuthOutcome::Unauthorized;
        }
        AuthOutcome::Allowed
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
    /// configurado, siempre `true` (barrera desactivada).
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
}
