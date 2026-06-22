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
//! **Decisiones que el humano debe revisar:**
//!   - **Sin `BRIDGE_TOKEN` configurado, la auth de token queda DESACTIVADA** (solo se aplica la
//!     allowlist de `Origin`). Es deliberado para no romper el arranque local en desarrollo, pero
//!     el binario loggea un `warn` ruidoso. En producción (sidecar/standalone empaquetado) el
//!     token SIEMPRE debe inyectarse. Alternativa si el humano prefiere fail-closed: exigir token
//!     siempre y que `main` aborte si falta.
//!   - **El `Origin` ausente se permite** (clientes nativos sin navegador — p.ej. pruebas, el
//!     sidecar local — no envían `Origin`). El token sigue siendo obligatorio si está configurado.
//!   - El secreto vive **solo** en el proceso del Bridge; nunca se loggea.

use axum::http::{HeaderMap, Uri};

/// Nombre de la cabecera propia de sesión del Hub (alternativa a `Authorization: Bearer`).
pub const SESSION_HEADER: &str = "x-hub-session";

/// Env var del secreto compartido del Bridge.
pub const ENV_TOKEN: &str = "BRIDGE_TOKEN";
/// Env var de orígenes extra permitidos (CSV). P.ej. `https://app.erplora.com,https://hub.local`.
pub const ENV_ALLOWED_ORIGINS: &str = "BRIDGE_ALLOWED_ORIGINS";

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
    /// Construye la política leyendo `BRIDGE_TOKEN` y `BRIDGE_ALLOWED_ORIGINS` del entorno.
    pub fn from_env() -> Self {
        let token = std::env::var(ENV_TOKEN).ok().filter(|t| !t.trim().is_empty());
        let extra_origins = std::env::var(ENV_ALLOWED_ORIGINS)
            .ok()
            .map(|csv| {
                csv.split(',')
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty())
                    .collect()
            })
            .unwrap_or_default();

        if token.is_none() {
            tracing::warn!(
                "{ENV_TOKEN} no configurado: el WS del Bridge NO exige token (solo allowlist de \
                 Origin). Configúralo en producción (sidecar/standalone empaquetado)."
            );
        }

        Self { token, extra_origins }
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
}
